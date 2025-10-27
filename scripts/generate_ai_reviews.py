import asyncio
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional
import argparse
import time
from datetime import datetime

try:
    from llm_client import LLMClient
except ImportError:
    logging.error("Failed to import LLMClient. Ensure llm_client.py is accessible.")
    raise

def load_config(config_path: str) -> Dict:
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"Failed to load config {config_path}: {e}")
        raise

def create_review_prompt(code_snippet: str, language: str) -> str:
    prompt = f"""You are a senior software engineer tasked with reviewing the following {language} code snippet for critical bugs, logic errors, memory leaks, null errors, security issues. Ignore style or formatting comments.

Code Snippet:

{code_snippet}

text

Provide a JSON response with keys:
"bugs_found": List of objects with "explanation" (bug description) and "suggested_fix" (code fix snippet).
If no bugs found, return empty list and "no_bugs_reasoning" explaining why.

Response must be strictly JSON-encoded.
"""
    return prompt

def get_code_snippet(item_metadata: Dict, data_root: Path) -> Optional[Dict[str, str]]:
    source = item_metadata.get("source", "unknown")
    code_info = {"code": None, "language": None}
    try:
        if source == "defects4j":
            source_files_path = Path(item_metadata.get("source_files_path", ""))
            buggy_files = list(source_files_path.glob("*_buggy.java"))
            if buggy_files:
                with open(buggy_files[0], "r", encoding="utf-8", errors="ignore") as f:
                    code_info["code"] = f.read()
                    code_info["language"] = "java"
            else:
                logging.warning(f"No buggy file found in {source_files_path}")
                return None
        elif source == "github":
            repo_name = item_metadata.get("repository")
            pr_id = item_metadata.get("id")
            pr_files_dir = data_root / "github_prs" / repo_name.replace("/", "_") / f"pr_{pr_id}_files"
            files_changed = item_metadata.get("files_changed", [])
            target_file = None
            for file_info in files_changed:
                filename = file_info.get("filename")
                status = file_info.get("status")
                if status == "modified" and filename and (filename.endswith(".py") or filename.endswith(".java")) and "test" not in filename.lower():
                    candidate = pr_files_dir / f"BEFORE_{filename.replace('/', '_')}"
                    if candidate.exists():
                        target_file = candidate
                        code_info["language"] = "python" if filename.endswith(".py") else "java"
                        break
            if target_file:
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    code_info["code"] = f.read()
            else:
                logging.warning(f"No suitable BEFORE file for PR {repo_name} #{pr_id}")
                return None
        elif source == "synthetic":
            mutated_file_path_str = item_metadata.get("mutated_file")
            if mutated_file_path_str:
                mutated_file_path = Path(mutated_file_path_str)
                if mutated_file_path.exists():
                    with open(mutated_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        code_info["code"] = f.read()
                        code_info["language"] = "java" if mutated_file_path.suffix == ".java" else "python"
                else:
                    logging.warning(f"Mutated file not found: {mutated_file_path}")
                    return None
            else:
                logging.warning("Missing mutated_file path for synthetic bug.")
                return None
        else:
            logging.warning(f"Unknown source type: {source}")
            return None
        
        # Truncate large snippets to 8k chars conservatively
        if code_info["code"] and len(code_info["code"]) > 8000:
            code_info["code"] = code_info["code"][:8000]
        
        if not code_info["code"] or not code_info["language"]:
            return None
        
        return code_info
    except Exception as e:
        logging.error(f"Error extracting code snippet for item {item_metadata.get('bug_id') or item_metadata.get('id')}: {e}")
        return None


async def generate_review_for_item(item_metadata: Dict, generator_model_id: str, llm_client: LLMClient, data_root: Path, output_dir: Path):
    item_id = item_metadata.get("bug_id") or item_metadata.get("id")
    source = item_metadata.get("source", "unknown")
    output_filename = f"{source}_{item_id}_review_{generator_model_id}.json"
    output_path = output_dir / output_filename
    
    if output_path.exists():
        logging.info(f"Skipping {output_filename}: already exists.")
        return
    
    code_info = get_code_snippet(item_metadata, data_root)
    if not code_info:
        logging.warning(f"Could not get code snippet for item {item_id}, skipping generation.")
        return
    
    prompt = create_review_prompt(code_info["code"], code_info["language"])
    
    try:
        raw_response = await asyncio.to_thread(
            llm_client.query_llm,
            model_id=generator_model_id,
            messages=[{"role": "user", "content": prompt}],
            use_json_mode=True,
            temperature=0.3,
            max_tokens=1024
        )
    except Exception as e:
        logging.error(f"API call failed for item {item_id} with model {generator_model_id}: {e}")
        return
    
    result_data = {
        "source_item_id": item_id,
        "source_type": source,
        "generator_model_id": generator_model_id,
        "generation_timestamp": datetime.now().isoformat(),
        "input_code_language": code_info["language"],
        "input_code_snippet": code_info["code"],
        "raw_llm_output": raw_response,
        "parsed_llm_output": None,
        "error": None
    }
    
    if raw_response:
        try:
            json_str = raw_response
            if raw_response.strip().startswith("```json"):
                json_str = raw_response.strip()[7:-3].strip()
            elif raw_response.strip().startswith("```"):
                json_str = raw_response.strip()[3:-3].strip()
            
            parsed = json.loads(json_str)
            if isinstance(parsed.get("bugs_found"), list) and isinstance(parsed.get("no_bugs_reasoning"), str):
                result_data["parsed_llm_output"] = parsed
            else:
                result_data["error"] = "Unexpected JSON structure in LLM output"
                logging.warning(f"Invalid JSON structure for {output_filename}: {json_str}")
        except json.JSONDecodeError:
            result_data["error"] = "Invalid JSON format in LLM output"
            logging.warning(f"JSON decode error for {output_filename}: {raw_response}")
        except Exception as e:
            result_data["error"] = f"Exception parsing LLM output: {e}"
            logging.error(f"Exception parsing output for {output_filename}: {e}")
    else:
        result_data["error"] = f"No response from LLM {generator_model_id}"
        logging.error(result_data["error"])
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved review results to {output_filename}")
    except Exception as e:
        logging.error(f"Failed to save review {output_filename}: {e}")


async def run_review_generation(config_path: str, output_dir: Path):
    config = load_config(config_path)
    data_root = Path(config["data"]["output_base"]).resolve()
    reviews_output_dir = output_dir.resolve()

    try:
        llm_client = LLMClient(config_path=config_path)
    except Exception as e:
        logging.critical(f"Failed to initialize LLMClient: {e}", exc_info=True)
        return

    generator_model_ids = [m["id"] for m in config.get("llm_models", []) if m.get("role") == "generator"]
    if not generator_model_ids:
        logging.critical("No generator models found in config.yaml. Exiting.")
        return

    all_items_metadata = []
    d4j_dir = data_root / "defects4j_bugs"
    if d4j_dir.is_dir():
        for f in d4j_dir.glob("*_metadata.json"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    meta = json.load(file)
                    meta["source"] = "defects4j"
                    all_items_metadata.append(meta)
            except Exception as e:
                logging.error(f"Failed to load Defects4J metadata {f.name}: {e}")
    gh_dir = data_root / "github_prs"
    if gh_dir.is_dir():
        for f in gh_dir.rglob("pr_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    meta = json.load(file)
                    meta["source"] = "github"
                    all_items_metadata.append(meta)
            except Exception as e:
                logging.error(f"Failed to load GitHub PR metadata {f.name}: {e}")
    synth_dir = data_root / "synthetic_bugs"
    for summary_file in synth_dir.glob("*_bugs_summary.json"):
        if summary_file.is_file():
            try:
                with open(summary_file, "r", encoding="utf-8") as file:
                    synth_bugs = json.load(file)
                    for bug_meta in synth_bugs:
                        bug_meta["source"] = "synthetic"
                        if "bug_id" not in bug_meta and "mutated_file" in bug_meta:
                            bug_meta["bug_id"] = Path(bug_meta["mutated_file"]).stem
                        all_items_metadata.append(bug_meta)
            except Exception as e:
                logging.error(f"Failed to load Synthetic bug metadata {summary_file.name}: {e}")

    if not all_items_metadata:
        logging.error("No items found for review generation. Check your dataset.")
        return

    logging.info(f"Loaded metadata for {len(all_items_metadata)} items across sources.")

    tasks = []
    semaphore = asyncio.Semaphore(3)

    async def run_with_limit(task):
        async with semaphore:
            await task

    for item_meta in all_items_metadata:
        for model_id in generator_model_ids:
            tasks.append(generate_review_for_item(item_meta, model_id, llm_client, data_root, reviews_output_dir))

    logging.info(f"Created {len(tasks)} generation tasks.")

    await asyncio.gather(*(run_with_limit(task) for task in tasks))

    logging.info("Completed all AI review generations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AI code reviews for dataset")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--output-dir", default="data/ai_reviews", help="Directory to save AI reviews")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
        force=True,
    )

    project_root = Path(".").resolve()
    config_file = project_root / args.config
    output_dir = project_root / args.output_dir

    if not config_file.exists():
        logging.critical(f"Config file missing: {config_file}")
        exit(1)
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Set AI reviews output directory: {output_dir}")

    logging.info("Starting AI Review Generation...")
    start_time = time.time()
    try:
        asyncio.run(run_review_generation(str(config_file), output_dir))
    except KeyboardInterrupt:
        logging.warning("Interrupted by user.")
    except Exception as err:
        logging.critical(f"Pipeline failed: {err}", exc_info=True)
    end_time = time.time()
    logging.info(f"Review generation completed in {end_time - start_time:.2f} seconds.")
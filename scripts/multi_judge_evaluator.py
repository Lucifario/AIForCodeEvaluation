import asyncio
import json
import logging
import yaml
from pathlib import Path
from typing import List,Dict,Optional
import argparse
import time,datetime
try:
    from llm_client import LLMClient
except ImportError:
    try:
        from llm_client import LLMClient
    except ImportError:
        logging.error("Failed to import LLMClient. Make sure llm_client.py is accessible.")
        raise
CRITERIA = ["factual_correctness", "actionability", "analytical_depth"]
SCORE_MIN = 1
SCORE_MAX = 5
class MultiJudgeEvaluator:
    """Orchestrates the multi-judge + meta-judge evaluation process."""
    def __init__(self, llm_client: LLMClient, config: Dict):
        """Initializes the evaluator."""
        self.client = llm_client
        self.config = config
        self.judge_model_ids = [m['id'] for m in config.get('llm_models', []) if m.get('role') == 'judge']
        meta_judge_models = [m['id'] for m in config.get('llm_models', []) if m.get('role') == 'meta-judge']
        if not self.judge_model_ids:
            raise ValueError("Config Error: No models found with role 'judge' in 'llm_models'.")
        if not meta_judge_models:
            raise ValueError("Config Error: No model found with role 'meta-judge' in 'llm_models'.")
        if len(meta_judge_models) > 1:
            logging.warning(f"Multiple meta-judges defined: {meta_judge_models}. Using the first one: {meta_judge_models[0]}")
        self.meta_judge_model_id = meta_judge_models[0]
        logging.info(f"Evaluator Initialized. Judges: {self.judge_model_ids}, Meta-Judge: {self.meta_judge_model_id}")
    def _create_judge_prompt(self, review_text: str, code_context: str = "") -> str:
        """Creates the detailed prompt for individual judge LLMs."""
        prompt = f"""You are an expert, impartial code review evaluator assessing an AI-generated code review comment.
Evaluate the comment based *only* on the provided information and the criteria definitions below.
**Evaluation Criteria (Score {SCORE_MIN}-{SCORE_MAX}):**
1.  **Factual Correctness ({SCORE_MIN}-{SCORE_MAX}):** Is the AI's observation/claim technically accurate regarding the provided code context? Ignore suggestions for now, just focus on the observation's accuracy.
    ({SCORE_MIN}=Completely incorrect/hallucinated. {SCORE_MAX}=Fully accurate and specific.)
2.  **Actionability ({SCORE_MIN}-{SCORE_MAX}):** Does the AI provide specific, useful, and directly implementable suggestions for improvement?
    ({SCORE_MIN}=No suggestion, or vague/generic/impossible advice. {SCORE_MAX}=Provides clear, concrete steps, code example, or specific alternative.)
3.  **Analytical Depth ({SCORE_MIN}-{SCORE_MAX}):** Does the comment demonstrate a deep understanding of the code's logic, potential issues, root causes, or broader implications? Does it go beyond surface-level observations (like style)?
    ({SCORE_MIN}=Superficial, obvious, style-only, or irrelevant comment. {SCORE_MAX}=Insightful analysis of root cause, impact, edge cases, or non-obvious alternatives/consequences.)

**Code Context Provided:**
{code_context if code_context else "No specific code context was provided. Evaluate based on the review comment's general plausibility and quality."}


**AI-Generated Review Comment to Evaluate:**
{review_text}


**Your Task:**
Provide integer scores ({SCORE_MIN}-{SCORE_MAX}) for each criterion. Also provide a brief, concise reasoning string explaining *why* you gave those scores, referencing the criteria definitions.

**Response Format:**
Your response MUST be ONLY a valid JSON object with the following exact keys and value types:
{{
  "factual_correctness": <score_integer>,
  "actionability": <score_integer>,
  "analytical_depth": <score_integer>,
  "reasoning": "<Concise justification string>"
}}
"""
        return prompt

    def _get_meta_judge_prompt(self, original_review: str, judge_outputs: List[Dict]) -> str:
        """Creates the prompt for the meta-judge LLM."""
        inputs_str = ""
        valid_judge_outputs = []
        for i, output in enumerate(judge_outputs):
            judge_id = output.get('judge_id', f'Judge_{i+1}')
            parsed = output.get('parsed_result')
            error = output.get('error')
            raw = output.get('raw_output', '')

            inputs_str += f"--- Judge: {judge_id} ---\n"
            if parsed:
                inputs_str += f"Scores: FC={parsed.get('factual_correctness', '?')}, A={parsed.get('actionability', '?')}, AD={parsed.get('analytical_depth', '?')}\n"
                inputs_str += f"Reasoning: {parsed.get('reasoning', 'N/A')}\n\n"
                valid_judge_outputs.append(output)
            elif error:
                inputs_str += f"Status: Error - {error}\n"
                inputs_str += f"Raw Output: '{raw[:150]}...' \n\n" if raw else "Raw Output: N/A\n\n"
            else:
                 inputs_str += f"Status: Invalid Output Format\n"
                 inputs_str += f"Raw Output: '{raw[:150]}...' \n\n" if raw else "Raw Output: N/A\n\n"
        prompt = f"""You are a Meta-Judge synthesizing evaluations from multiple AI judges about an AI-generated code review comment. Your goal is to determine the most reliable consensus evaluation.

**Original AI-Generated Review Comment:**
{original_review}


**Individual Judge Evaluations Received:**
{inputs_str}

**Your Meta-Evaluation Task (Chain of Thought):**
1.  **Analyze Agreement/Disagreement:** Briefly note the level of agreement or disagreement among the valid judge responses for each criterion (Factual Correctness, Actionability, Analytical Depth). Mention any outliers or conflicting reasoning.
2.  **Synthesize Factual Correctness:** Based on the judges' scores and reasoning, determine the most plausible final score ({SCORE_MIN}-{SCORE_MAX}) for Factual Correctness. Justify your choice, especially if handling disagreement.
3.  **Synthesize Actionability:** Similarly, determine and justify the final score ({SCORE_MIN}-{SCORE_MAX}) for Actionability.
4.  **Synthesize Analytical Depth:** Similarly, determine and justify the final score ({SCORE_MIN}-{SCORE_MAX}) for Analytical Depth.
5.  **Final Summary:** Provide a concise overall summary of your synthesis process and final scores.

**Response Format:**
Your response MUST be ONLY a valid JSON object containing your final synthesis, following this exact structure:
{{
  "analysis": "<Your brief analysis of judge agreement/disagreement - Step 1>",
  "final_factual_correctness": <consensus_score_integer_step_2>,
  "final_actionability": <consensus_score_integer_step_3>,
  "final_analytical_depth": <consensus_score_integer_step_4>,
  "consensus_reasoning": "<Your final summary justification for all scores - Step 5>"
}}
"""
        return prompt

    async def _run_single_judge(self, judge_id: str, prompt: str) -> Dict:
        """Calls a single judge LLM asynchronously using the client."""
        logging.debug(f"Calling judge: {judge_id}")
        raw_output = await asyncio.to_thread(
            self.client.query_llm,
            model_id=judge_id,
            messages=[{"role": "user", "content": prompt}],
            use_json_mode=True,
            temperature=0.1
        )

        result = {"judge_id": judge_id, "raw_output": raw_output, "parsed_result": None, "error": None}
        if raw_output:
            try:
                if raw_output.strip().startswith("```json"):
                    cleaned_output = raw_output.strip()[7:-3].strip()
                elif raw_output.strip().startswith("```"):
                     cleaned_output = raw_output.strip()[3:-3].strip()
                else:
                    cleaned_output = raw_output.strip()
                parsed = json.loads(cleaned_output)
                valid = True
                if not isinstance(parsed, dict): valid = False
                if not all(k in parsed for k in CRITERIA + ["reasoning"]): valid = False
                if not all(isinstance(parsed[k], int) for k in CRITERIA): valid = False
                if not all(SCORE_MIN <= parsed[k] <= SCORE_MAX for k in CRITERIA): valid = False
                if not isinstance(parsed.get("reasoning"), str): valid = False
                if valid:
                    result["parsed_result"] = parsed
                else:
                    result["error"] = "Output JSON structure, type, or score range invalid"
                    logging.warning(f"Judge {judge_id} invalid JSON content: {cleaned_output} -> {result['error']}")
            except json.JSONDecodeError:
                result["error"] = "Invalid JSON format"
                logging.warning(f"Judge {judge_id} invalid JSON format: {raw_output}")
            except Exception as e:
                result["error"] = f"Unexpected parsing error: {str(e)}"
                logging.error(f"Judge {judge_id} parsing error: {e}", exc_info=True)
        else:
            result["error"] = f"No response from judge {judge_id} after retries."
            logging.error(result["error"])
        return result

    async def _run_meta_judge(self, original_review: str, judge_outputs: List[Dict]) -> Dict:
        """Calls the meta-judge LLM asynchronously using the client."""
        if not judge_outputs:
             logging.error("Meta-judge called with no judge outputs.")
             return {"raw_output": None, "parsed_result": None, "error": "No judge outputs provided."}
        logging.debug(f"Calling meta-judge: {self.meta_judge_model_id}")
        prompt = self._get_meta_judge_prompt(original_review, judge_outputs)
        raw_output = await asyncio.to_thread(
            self.client.query_llm,
            model_id=self.meta_judge_model_id,
            messages=[{"role": "user", "content": prompt}],
            use_json_mode=True,
            temperature=0.2
        )
        result = {"model_id": self.meta_judge_model_id, "raw_output": raw_output, "parsed_result": None, "error": None}
        if raw_output:
            try:
                if raw_output.strip().startswith("```json"):
                    cleaned_output = raw_output.strip()[7:-3].strip()
                elif raw_output.strip().startswith("```"):
                     cleaned_output = raw_output.strip()[3:-3].strip()
                else:
                    cleaned_output = raw_output.strip()
                parsed = json.loads(cleaned_output)
                meta_criteria = [f"final_{c}" for c in CRITERIA]
                valid = True
                if not isinstance(parsed, dict): valid = False
                if not all(k in parsed for k in meta_criteria + ["analysis", "consensus_reasoning"]): valid = False
                if not all(isinstance(parsed[k], int) for k in meta_criteria): valid = False
                if not all(SCORE_MIN <= parsed[k] <= SCORE_MAX for k in meta_criteria): valid = False
                if not all(isinstance(parsed[k], str) for k in ["analysis", "consensus_reasoning"]): valid = False
                if valid:
                    result["parsed_result"] = parsed
                else:
                    result["error"] = "Output JSON structure, type, or score range invalid"
                    logging.warning(f"Meta-Judge invalid JSON content: {cleaned_output} -> {result['error']}")
            except json.JSONDecodeError:
                result["error"] = "Invalid JSON format"
                logging.warning(f"Meta-Judge invalid JSON format: {raw_output}")
            except Exception as e:
                result["error"] = f"Unexpected parsing error: {str(e)}"
                logging.error(f"Meta-Judge parsing error: {e}", exc_info=True)
        else:
            result["error"] = f"No response from meta-judge {self.meta_judge_model_id} after retries."
            logging.error(result["error"])

        return result

    async def evaluate_review_consensus(self, review_text: str, code_context: str = "") -> Dict:
        """
        Main orchestration method for evaluating one review using multi-judge consensus.
        """
        start_time = time.time()
        logging.info("Starting multi-judge consensus evaluation...")
        judge_prompt = self._create_judge_prompt(review_text, code_context)
        judge_tasks = [self._run_single_judge(judge_id, judge_prompt) for judge_id in self.judge_model_ids]
        individual_judge_results = await asyncio.gather(*judge_tasks)
        logging.info(f"Received {len(individual_judge_results)} judge results.")
        meta_judge_result = await self._run_meta_judge(review_text, individual_judge_results)
        logging.info(f"Received meta-judge result.")
        evaluation_result = {
            "original_review": review_text,
            "code_context_provided": bool(code_context),
            "evaluation_timestamp": datetime.datetime.now().isoformat(),
            "judges": individual_judge_results,
            "meta_judge": meta_judge_result,
            "duration_seconds": time.time() - start_time
        }

        logging.info(f"Consensus evaluation completed in {evaluation_result['duration_seconds']:.2f} seconds.")
        return evaluation_result
def load_review_data(review_file_path: Path) -> Optional[Dict[str, str]]:
    """Loads review data, extracting meaningful review text and context."""
    try:
        with open(review_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        review_text_to_judge = None
        error_during_generation = data.get("error")
        parsed_output = data.get("parsed_llm_output")
        raw_output = data.get("raw_llm_output")
        code_context = data.get("code_context", "")
        if error_during_generation:
            logging.warning(f"Skipping {review_file_path.name}: Generation script reported error: {error_during_generation}")
            return None
        if isinstance(parsed_output, dict):
            bugs = parsed_output.get("bugs_found")
            no_bugs_reasoning = parsed_output.get("no_bugs_reasoning", "")

            if isinstance(bugs, list) and bugs:
                formatted_review = "Bugs Found:\n"
                for i, bug in enumerate(bugs):
                    expl = bug.get("explanation", "N/A")
                    fix = bug.get("suggested_fix", "N/A")
                    formatted_review += f"{i+1}. Explanation: {expl}\n   Suggested Fix: {fix}\n"
                review_text_to_judge = formatted_review.strip()
            elif isinstance(no_bugs_reasoning, str) and no_bugs_reasoning.strip():
                review_text_to_judge = f"No Bugs Found Reasoning: {no_bugs_reasoning}"
            else:
                 logging.warning(f"Parsed output in {review_file_path.name} has unexpected structure: {parsed_output}. Falling back to raw output.")
        if review_text_to_judge is None:
            if isinstance(raw_output, str) and raw_output.strip():
                review_text_to_judge = raw_output
                try:
                    parsed_fallback = json.loads(raw_output)
                    logging.debug(f"Successfully parsed raw_output fallback for {review_file_path.name}")
                except:
                    logging.debug(f"Raw output for {review_file_path.name} used directly as it wasn't valid JSON.")
                    pass
            else:
                 logging.error(f"Could not extract any review text (parsed or raw) from {review_file_path.name}")
                 return None
        max_context = 2000
        if len(code_context) > max_context:
            code_context = code_context[:max_context // 2] + "\n...\n" + code_context[-max_context // 2:]
        return {"review_text": review_text_to_judge, "code_context": code_context}
    except json.JSONDecodeError:
        logging.warning(f"Skipping {review_file_path.name}: Invalid JSON.")
        return None
    except Exception as e:
        logging.error(f"Error loading or processing review file {review_file_path.name}: {e}", exc_info=True)
        return None

async def run_evaluation_pipeline(config_path: str, reviews_input_dir: Path, eval_output_dir: Path):
    """Initializes client and evaluator, then processes all review files."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"Failed to load or parse config file {config_path}: {e}")
        return
    try:
        llm_client = LLMClient(config_path=config_path)
        evaluator = MultiJudgeEvaluator(llm_client, config)
    except Exception as e:
        logging.critical(f"Failed to initialize LLMClient or MultiJudgeEvaluator: {e}", exc_info=True)
        return
    review_files = list(reviews_input_dir.rglob('*.json'))
    if not review_files:
        logging.warning(f"No potential review files (*.json) found in {reviews_input_dir}. Nothing to evaluate.")
        return
    logging.info(f"Found {len(review_files)} potential review files to process.")
    semaphore = asyncio.Semaphore(10)

    async def process_file_with_limit(file_path):
        async with semaphore:
            logging.debug(f"Acquired semaphore for {file_path.name}")
            review_data = load_review_data(file_path)
            if review_data:
                results = await evaluator.evaluate_review_consensus(
                    review_data["review_text"],
                    review_data["code_context"]
                )
                output_filename = f"{file_path.stem}_qualitative_eval.json"
                output_path = eval_output_dir / output_filename
                try:
                    eval_output_dir.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    logging.info(f"Saved evaluation: {output_path.name}")
                except Exception as e:
                     logging.error(f"Failed to save results for {file_path.name} to {output_path}: {e}")
            logging.debug(f"Released semaphore for {file_path.name}")

    tasks = [process_file_with_limit(file_path) for file_path in review_files]
    await asyncio.gather(*tasks)

    logging.info(f"Finished processing {len(review_files)} files.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Multi-Judge Qualitative Evaluation using Free LLMs")
    parser.add_argument('--config', default='config/config.yaml', help='Path to the main config file.')
    parser.add_argument('--reviews-dir', default='data/ai_reviews', help='Directory containing AI-generated review files (JSON format).')
    parser.add_argument('--output-dir', default='data/evaluation_metrics/qualitative', help='Directory to save qualitative evaluation results (JSON format).')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Set logging level.')
    args = parser.parse_args()
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    log_format = '%(asctime)s - %(levelname)-8s - %(message)s'
    logging.basicConfig(level=log_level, format=log_format, handlers=[logging.StreamHandler()], force=True)
    project_root = Path('.').resolve()
    config_file = project_root / args.config
    reviews_input = project_root / args.reviews_dir
    eval_output = project_root / args.output_dir
    if not config_file.exists():
        logging.critical(f"CRITICAL ERROR: Config file not found at {config_file}")
        exit(1)
    if not reviews_input.is_dir():
        logging.critical(f"CRITICAL ERROR: Reviews input directory not found or not a directory: {reviews_input}")
        exit(1)
    eval_output.mkdir(parents=True, exist_ok=True)
    logging.info(f"Ensured output directory exists: {eval_output}")
    logging.info("--- Starting Multi-Judge Evaluation Pipeline ---")
    start_run_time = time.time()
    try:
        asyncio.run(run_evaluation_pipeline(str(config_file), reviews_input, eval_output))
        end_run_time = time.time()
        logging.info(f"--- Pipeline completed successfully in {end_run_time - start_run_time:.2f} seconds ---")
    except KeyboardInterrupt:
        logging.warning("Pipeline interrupted by user.")
    except Exception as e:
        logging.critical(f"--- Pipeline failed with CRITICAL error: {e} ---", exc_info=True)
        exit(1)
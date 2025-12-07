import asyncio
import json
import logging
import yaml
import sys
from pathlib import Path
import argparse
from datetime import datetime

try:
    from llm_client import LLMClient
    from qodo_integration import QodoClient
    from code_chunker import CodeChunker
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from llm_client import LLMClient
    from qodo_integration import QodoClient
    from code_chunker import CodeChunker

# ... (Keep load_config and create_review_prompt from before) ...
def load_config(config_path):
    with open(config_path) as f: return yaml.safe_load(f)

def create_review_prompt(code, lang):
    return f"Review this {lang} code for bugs. Return JSON with 'bugs' list.\n\nCode:\n```{lang}\n{code}```"

async def process_item(item, models, llm_client, qodo_client, output_dir):
    sample_id = item['id']
    
    # 1. Get Code Path from Clean Dataset
    path = Path(item['source_files_path'])
    
    # Find the file (Greedy search for BEFORE/Buggy)
    files = list(path.glob('BEFORE_*')) + list(path.glob('*_buggy.java')) + list(path.glob('*.py'))
    if not files: return
    
    target_file = files[0]
    code = target_file.read_text(errors='ignore')
    lang = 'python' if target_file.suffix == '.py' else 'java'

    # 2. Generate Reviews
    for model in models:
        model_id = model['id']
        out_file = output_dir / f"{sample_id}_{model_id.replace('/', '_')}.json"
        if out_file.exists(): continue

        review_data = {}
        try:
            if model_id == 'qodo-cli':
                review_data = await asyncio.to_thread(qodo_client.review_code_string, code, lang)
            else:
                # LLM
                prompt = create_review_prompt(code[:6000], lang) # Truncate to fit
                response = await asyncio.to_thread(llm_client.query_llm, model_id, [{"role":"user", "content":prompt}], True)
                review_data = {"response": response}
                
            # Save
            with open(out_file, 'w') as f:
                json.dump({
                    "sample_id": sample_id,
                    "model": model_id,
                    "code_context": code, # Key for evaluator
                    "review": review_data
                }, f)
            logging.info(f"✓ Saved {out_file.name}")
            
        except Exception as e:
            logging.error(f"Failed {sample_id}: {e}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/config.yaml')
    parser.add_argument('--dataset', default='data/phase1_results/unified_dataset_clean.json') # Default to CLEAN
    parser.add_argument('--output', default='data/ai_reviews')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    # Load Data
    with open(args.dataset) as f: data = json.load(f)
    logging.info(f"Loaded {len(data)} samples.")
    
    # Setup
    config = load_config(args.config)
    llm = LLMClient(args.config)
    qodo = QodoClient()
    Path(args.output).mkdir(exist_ok=True)
    
    models = [m for m in config['llm_models'] if m['role'] == 'generator']
    models.append({'id': 'qodo-cli'})

    # Run with concurrency limit
    sem = asyncio.Semaphore(5)
    async def runner(item):
        async with sem: await process_item(item, models, llm, qodo, Path(args.output))
    
    await asyncio.gather(*(runner(i) for i in data))

if __name__ == '__main__':
    asyncio.run(main())
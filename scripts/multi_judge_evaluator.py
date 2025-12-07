import asyncio
import json
import logging
import yaml
import random
from pathlib import Path
from typing import List, Dict
import argparse
import time
import datetime
import sys

try:
    from llm_client import LLMClient
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from llm_client import LLMClient

CRITERIA = [
    "factual_correctness",
    "actionability",
    "analytical_depth",
    "security_awareness",
    "constructiveness",
    "adherence_to_guidelines"
]
SCORE_MIN = 1
SCORE_MAX = 5

class MultiJudgeEvaluator:
    def __init__(self, llm_client: LLMClient, config: Dict):
        self.client = llm_client
        self.config = config
        self.judge_models = [m['id'] for m in config.get('llm_models', []) if m.get('role') == 'judge']
        meta_judges = [m['id'] for m in config.get('llm_models', []) if m.get('role') == 'meta-judge']
        
        if not self.judge_models:
            raise ValueError("Config Error: No 'judge' models found.")
        if not meta_judges:
            raise ValueError("Config Error: No 'meta-judge' models found.")
            
        self.meta_judge = meta_judges[0]
        logging.info(f"Evaluator Initialized. Judges: {self.judge_models}, Meta: {self.meta_judge}")

    def _create_judge_prompt(self, review_text: str, code_context: str = "") -> str:
        return f"""You are an expert code review evaluator. Score the following review on a 1-5 scale.

**Evaluation Criteria (1-5):**
1. **Factual Correctness:** Is the feedback technically accurate? (1=Hallucinated, 5=Perfectly Accurate)
2. **Actionability:** Are suggestions concrete? (1=Vague, 5=Ready-to-copy code)
3. **Analytical Depth:** Root cause analysis? (1=Surface level, 5=Deep insight)
4. **Security Awareness:** Identifies security risks? (1=Ignored, 5=Explicit check)
5. **Constructiveness:** Does it offer improvements rather than just criticism? (1=Negative/Nits, 5=Positive/Helpful)
6. **Guideline Adherence:** Did it follow constraints? (1=Violated, 5=Perfect)

**Code Context:**
{code_context[:3000]}... (truncated)

**Review to Evaluate:**
{review_text[:6000]}

**Output JSON ONLY:**
{{
  "factual_correctness": <int>,
  "actionability": <int>,
  "analytical_depth": <int>,
  "security_awareness": <int>,
  "constructiveness": <int>,
  "adherence_to_guidelines": <int>,
  "reasoning": "<string>"
}}
"""

    def _create_meta_judge_prompt(self, original_review: str, judge_outputs: List[Dict]) -> str:
        inputs_str = ""
        shuffled_judges = judge_outputs.copy()
        random.shuffle(shuffled_judges)
        
        for i, output in enumerate(shuffled_judges):
            judge_id = output.get('judge_id', f'Judge_{i+1}')
            parsed = output.get('parsed_result')
            
            inputs_str += f"--- Judge {i+1} ({judge_id}) ---\n"
            if parsed:
                scores = ", ".join([f"{k}={v}" for k, v in parsed.items() if isinstance(v, (int, float))])
                inputs_str += f"Scores: {{{scores}}}\nReasoning: {parsed.get('reasoning', 'N/A')}\n\n"
            else:
                inputs_str += "Status: Failed/Invalid Output\n\n"

        return f"""Synthesize these judge evaluations into a final consensus.
        
Original Review:
{original_review[:1500]}...

Judge Evaluations:
{inputs_str}

Task: Determine the most reliable consensus score for each metric (1-5).
Return JSON ONLY:
{{
  "final_factual_correctness": <int>,
  "final_actionability": <int>,
  "final_analytical_depth": <int>,
  "final_security_awareness": <int>,
  "final_constructiveness": <int>,
  "final_adherence_to_guidelines": <int>,
  "consensus_reasoning": "<summary>"
}}
"""

    async def _run_single_judge(self, judge_id: str, prompt: str) -> Dict:
        raw_output = await asyncio.to_thread(
            self.client.query_llm,
            model_id=judge_id,
            messages=[{"role": "user", "content": prompt}],
            use_json_mode=True,
            temperature=0.1
        )

        result = {"judge_id": judge_id, "parsed_result": None}
        if raw_output:
            try:
                clean = raw_output.strip().replace('```json', '').replace('```', '')
                result["parsed_result"] = json.loads(clean)
            except: pass
        return result

    async def evaluate_review_consensus(self, review_text: str, code_context: str = "") -> Dict:
        start_time = time.time()
        
        # 1. Run Judges
        judge_prompt = self._create_judge_prompt(review_text, code_context)
        judge_tasks = [self._run_single_judge(jid, judge_prompt) for jid in self.judge_models]
        individual_results = await asyncio.gather(*judge_tasks)
        
        # 2. Run Meta-Judge
        meta_prompt = self._create_meta_judge_prompt(review_text, individual_results)
        meta_raw = await asyncio.to_thread(
            self.client.query_llm,
            model_id=self.meta_judge,
            messages=[{"role": "user", "content": meta_prompt}],
            use_json_mode=True,
            temperature=0.2
        )

        meta_parsed = None
        if meta_raw:
            try:
                clean = meta_raw.strip().replace('```json', '').replace('```', '')
                meta_parsed = json.loads(clean)
            except: pass

        return {
            "original_review": review_text,
            "judges": individual_results,
            "meta_judge": {"parsed_result": meta_parsed, "raw_output": meta_raw},
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.datetime.now().isoformat()
        }

async def run_evaluation_pipeline(config_path: str, reviews_input_dir: Path, eval_output_dir: Path):
    with open(config_path, 'r') as f: config = yaml.safe_load(f)
    client = LLMClient(config_path)
    evaluator = MultiJudgeEvaluator(client, config)
    
    if not reviews_input_dir.exists():
        logging.error(f"Input directory not found: {reviews_input_dir}")
        return

    files = list(reviews_input_dir.glob('*.json'))
    logging.info(f"Found {len(files)} review files to evaluate.")
    
    sem = asyncio.Semaphore(5)
    
    async def process(file_path):
        # Skip if already evaluated
        out_file = eval_output_dir / f"{file_path.stem}_qualitative_eval.json"
        if out_file.exists(): return

        async with sem:
            try:
                with open(file_path) as f: data = json.load(f)
                
                # --- FIX: Handle Qodo 'raw_output' key ---
                review_text = ""
                if isinstance(data.get('review'), dict):
                    # Try standard 'response' first, then 'raw_output' (for Qodo)
                    review_text = data['review'].get('response') or data['review'].get('raw_output', '')
                    
                    # Handle parsed JSON stored as object
                    if not review_text and 'parsed_llm_output' in data:
                         review_text = json.dumps(data['parsed_llm_output'])
                
                if not review_text: 
                    # logging.warning(f"No review text found in {file_path.name}")
                    return

                results = await evaluator.evaluate_review_consensus(
                    review_text, 
                    data.get('code_context', '')
                )
                
                results['model_evaluated'] = data.get('model_id', 'unknown')
                
                with open(out_file, 'w') as f: json.dump(results, f, indent=2)
                logging.info(f"✓ Evaluated {file_path.name}")
                
            except Exception as e:
                logging.error(f"Failed {file_path.name}: {e}")

    await asyncio.gather(*(process(f) for f in files))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/config.yaml')
    parser.add_argument('--reviews-dir', default='data/ai_reviews')
    parser.add_argument('--output-dir', default='data/evaluation_metrics/qualitative')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    asyncio.run(run_evaluation_pipeline(args.config, Path(args.reviews_dir), Path(args.output_dir)))
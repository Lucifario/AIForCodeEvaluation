import json
import logging
import argparse
import difflib
import pandas as pd
import numpy as np
from pathlib import Path
from radon.complexity import cc_visit
import matplotlib.pyplot as plt
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def calculate_complexity(code):
    try:
        return sum(c.complexity for c in cc_visit(code))
    except:
        return 0

def get_ground_truth_changes(before_code, after_code):
    d = difflib.Differ()
    diff = list(d.compare(before_code.splitlines(), after_code.splitlines()))
    changed_lines = set()
    current_line = 0
    for line in diff:
        if line.startswith('  ') or line.startswith('- '):
            current_line += 1
        if line.startswith('- ') or (line.startswith('+ ') and not line.startswith('  ')):
            changed_lines.add(current_line)
    return changed_lines

def calculate_similarity(str1, str2):
    if not str1 or not str2: return 0.0
    return difflib.SequenceMatcher(None, str1, str2).ratio()

def extract_json_from_text(text):
    """Extracts JSON object from a string, handling markdown blocks"""
    try:
        # Try simple parse
        return json.loads(text)
    except:
        # Try finding code blocks
        try:
            if "```json" in text:
                content = text.split("```json")[1].split("```")[0]
                return json.loads(content)
            elif "```" in text:
                content = text.split("```")[1].split("```")[0]
                return json.loads(content)
        except:
            pass
    return {}

def run_analysis(reviews_dir, dataset_path, output_dir):
    print(f"\nLoading dataset map from {dataset_path}...")
    try:
        with open(dataset_path, 'r') as f:
            dataset_list = json.load(f)
            dataset = {item['id']: item for item in dataset_list}
    except FileNotFoundError:
        print(f"❌ Dataset not found: {dataset_path}")
        return

    print(f"Scanning reviews in {reviews_dir}...")
    review_files = list(Path(reviews_dir).glob('*.json'))
    
    results = []
    
    for review_file in review_files:
        try:
            with open(review_file, 'r') as f:
                review_data = json.load(f)
            
            sample_id = review_data.get('sample_id')
            # Handle mismatch: file might use 'model' or 'model_id'
            model = review_data.get('model') or review_data.get('model_id', 'unknown')
            
            if not sample_id or sample_id not in dataset: continue
            item = dataset[sample_id]

            # --- 1. Get Ground Truth ---
            path_str = item.get('source_files_path')
            if not path_str: continue
            source_path = Path(path_str)
            
            if not source_path.exists():
                # Try relative paths
                prefixes = ['data/defects4j_aggressive', 'data/github_prs_aggressive', 'data']
                for p in prefixes:
                    if (Path(p) / source_path.name).exists():
                        source_path = Path(p) / source_path.name
                        break
            
            if not source_path.exists(): continue

            before_file = next(source_path.glob('BEFORE_*'), None) or next(source_path.glob('*_buggy.java'), None)
            after_file = next(source_path.glob('AFTER_*'), None) or next(source_path.glob('*_fixed.java'), None)

            # Fallback for single file repos (Python usually)
            if not before_file and source_path.is_dir():
                 py = list(source_path.glob('*.py'))
                 if py: before_file = py[0]

            if not before_file or not after_file: continue

            before_code = before_file.read_text(errors='ignore')
            after_code = after_file.read_text(errors='ignore')
            ground_truth_lines = get_ground_truth_changes(before_code, after_code)

            # --- 2. Extract AI Predictions (FIXED LOGIC) ---
            ai_lines = set()
            ai_fix_code = ""
            
            # Extract the text response
            response_text = ""
            if isinstance(review_data.get('review'), dict):
                response_text = review_data['review'].get('response', '')
            elif 'parsed_llm_output' in review_data:
                # It might already be parsed
                response_text = json.dumps(review_data['parsed_llm_output'])
            
            # Try to parse JSON from the text
            parsed = extract_json_from_text(response_text)
            
            # If parsing worked, extract bugs
            if isinstance(parsed, dict):
                bugs = parsed.get('bugs') or parsed.get('bugs_found')
                if isinstance(bugs, list):
                    for bug in bugs:
                        # Extract line
                        line = bug.get('line')
                        if isinstance(line, int): ai_lines.add(line)
                        elif isinstance(line, str) and line.isdigit(): ai_lines.add(int(line))
                        # Extract fix
                        fix = bug.get('fix') or bug.get('suggested_fix')
                        if fix: ai_fix_code += str(fix) + "\n"

            # --- 3. Calculate Metrics ---
            hits = 0
            for ai_line in ai_lines:
                if any(abs(ai_line - gt) <= 5 for gt in ground_truth_lines):
                    hits += 1
            
            precision = hits / len(ai_lines) if ai_lines else 0.0
            recall = hits / len(ground_truth_lines) if ground_truth_lines else 0.0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            
            fix_sim = 0.0
            if ai_fix_code:
                if ai_fix_code.strip() in after_code: fix_sim = 1.0
                else: fix_sim = calculate_similarity(ai_fix_code, after_code)

            results.append({
                "Model": model,
                "Precision": precision,
                "Recall": recall,
                "F1": f1,
                "Fix_Similarity": fix_sim
            })
            
        except Exception as e:
            pass

    if not results:
        print(f"❌ No quantitative results calculated.")
        return

    df = pd.DataFrame(results)
    
    print("\n" + "="*60)
    print(f"QUANTITATIVE RESULTS (Based on {len(results)} valid comparisons)")
    print("="*60)
    
    summary = df.groupby('Model')[['Precision', 'Recall', 'F1', 'Fix_Similarity']].mean()
    print(summary.to_markdown(floatfmt=".4f"))

    Path(output_dir).mkdir(exist_ok=True)
    df.to_csv(f"{output_dir}/quantitative_results.csv", index=False)

if __name__ == '__main__':
    run_analysis('data/ai_reviews', 'data/phase1_results/unified_dataset_clean.json', 'charts')
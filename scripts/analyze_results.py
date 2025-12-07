import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
import numpy as np
from pathlib import Path
from sklearn.metrics import cohen_kappa_score

QUAL_CRITERIA = ["factual_correctness", "actionability", "analytical_depth", 
                 "security_awareness", "constructiveness", "adherence_to_guidelines"]

def load_data(data_dir):
    records = []
    files = list(Path(data_dir).glob('*_eval.json'))
    print(f"Loading {len(files)} evaluation files...")
    
    for f in files:
        try:
            with open(f) as jf:
                entry = json.load(jf)
                
                # 1. Recover Model Name from Filename if unknown
                model = entry.get('model_evaluated', 'unknown')
                if model == 'unknown':
                    # Filename: SampleID_ModelName_qualitative_eval.json
                    # e.g., Lang_30_llama3-8b-groq_qualitative_eval.json
                    name_parts = f.name.replace('_qualitative_eval.json', '').split('_')
                    # Heuristic: Model names usually contain '-' (llama-3, mistral-nemo)
                    # Sample IDs usually don't have '-' in the middle of words
                    # Let's try to split by known model patterns or just take the last few parts
                    if 'llama' in f.name: model = 'llama3-8b-groq' # Simplified mapping
                    elif 'mistral' in f.name: model = 'mistral-nemo'
                    elif 'qwen' in f.name: model = 'qwen-coder-32b'
                    elif 'qodo' in f.name: model = 'qodo-cli'

                # 2. Scores (Meta or Fallback)
                meta = entry.get('meta_judge', {}).get('parsed_result', {})
                row = {'model': model, 'latency': entry.get('duration_seconds', 0)}
                
                if meta:
                    for c in QUAL_CRITERIA:
                        row[c] = float(meta.get(f'final_{c}', 0))
                else:
                    # Fallback to average
                    judges = entry.get('judges', [])
                    scores = {c: [] for c in QUAL_CRITERIA}
                    for j in judges:
                        p = j.get('parsed_result', {}) or {}
                        for c in QUAL_CRITERIA:
                            if p.get(c): scores[c].append(float(p[c]))
                    
                    valid = False
                    for c in QUAL_CRITERIA:
                        if scores[c]:
                            row[c] = sum(scores[c]) / len(scores[c])
                            valid = True
                    if not valid: continue

                # 3. Kappa Data
                judges = entry.get('judges', [])
                if len(judges) >= 2:
                    j1 = judges[0].get('parsed_result', {}) or {}
                    j2 = judges[1].get('parsed_result', {}) or {}
                    row['j1_fact'] = j1.get('factual_correctness')
                    row['j2_fact'] = j2.get('factual_correctness')

                records.append(row)
        except: pass
            
    return pd.DataFrame(records)

def calculate_kappa(df):
    df = df.dropna(subset=['j1_fact', 'j2_fact'])
    if len(df) < 5: return 0
    try:
        return cohen_kappa_score(df['j1_fact'].astype(int), df['j2_fact'].astype(int))
    except: return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/evaluation_metrics/qualitative")
    parser.add_argument("--output-dir", default="charts")
    args = parser.parse_args()
    
    df = load_data(args.data_dir)
    if df.empty:
        print("No data found.")
        return
        
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    print("\n=== QUALITATIVE RESULTS ===")
    summary = df.groupby('model')[QUAL_CRITERIA].mean()
    print(summary.to_markdown(floatfmt=".2f"))
    
    print(f"\nOverall Kappa: {calculate_kappa(df):.4f}")
    
    # Save
    plt.figure(figsize=(12, 6))
    sns.heatmap(summary, annot=True, cmap='viridis', fmt=".2f", vmin=1, vmax=5)
    plt.title("AI Review Quality")
    plt.tight_layout()
    plt.savefig(f"{args.output_dir}/qualitative_heatmap.png")
    print(f"✓ Saved heatmap to {args.output_dir}")

if __name__ == "__main__":
    main()
import logging
import os
import json
import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
from pathlib import Path
import re
SCORE_MIN = 1
SCORE_MAX = 5
QUAL_CRITERIA = ["factual_correctness", "actionability", "analytical_depth"]
FINAL_SCORE_KEYS = [f"final_{c}" for c in QUAL_CRITERIA]
QUAL_CRITERIA = ["factual_correctness", "actionability", "analytical_depth"]
FINAL_SCORE_KEYS = [f"final_{c}" for c in QUAL_CRITERIA]
def load_evaluation_files(directory_path: Path) -> list:
    """Loads all *_qualitative_eval.json files from the directory."""
    all_data = []
    print(f"Loading evaluation JSON files from: {directory_path}")
    files_to_load = list(directory_path.glob('*_qualitative_eval.json'))
    if not files_to_load:
         print(f"Warning: No '*_qualitative_eval.json' files found in {directory_path}")
         return []

    for file_path in files_to_load:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['source_filename'] = file_path.name
                all_data.append(data)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {file_path.name}. Skipping.")
        except Exception as e:
            print(f"An error occurred loading file {file_path.name}: {e}")
    print(f"Successfully loaded {len(all_data)} evaluation records.")
    return all_data

def preprocess_data(raw_data: list) -> pd.DataFrame:
    """Extracts key metrics from raw multi-judge output into a structured DataFrame."""
    processed_records = []
    print("Preprocessing loaded data...")
    filename_pattern = re.compile(r"^(?P<source>.*?)_(?P<item_id>.*?)_review_(?P<generator_id>.*?)_qualitative_eval\.json$")
    for record in raw_data:
        processed = {}
        filename = record.get('source_filename', '')
        match = filename_pattern.match(filename)
        if match:
             processed['source'] = match.group('source')
             processed['item_id'] = match.group('item_id')
             processed['generator_model_id'] = match.group('generator_id')
        else:
             processed['source'] = 'unknown'
             processed['item_id'] = filename
             processed['generator_model_id'] = 'unknown'
             print(f"Warning: Could not parse filename '{filename}' to extract metadata.")
        processed['original_review'] = record.get('original_review', '')
        processed['evaluation_timestamp'] = record.get('evaluation_timestamp')
        processed['latency_seconds'] = record.get('duration_seconds')
        meta_judge_result = record.get('meta_judge', {})
        meta_parsed = meta_judge_result.get('parsed_result')
        meta_error = meta_judge_result.get('error')
        processed['meta_judge_error'] = bool(meta_error)
        processed['meta_judge_raw'] = meta_judge_result.get('raw_output')
        if meta_parsed and not meta_error:
            for criterion in QUAL_CRITERIA:
                processed[f'{criterion}_score'] = meta_parsed.get(f'final_{criterion}')
            processed['meta_judge_reasoning'] = meta_parsed.get('consensus_reasoning')
            processed['meta_judge_analysis'] = meta_parsed.get('analysis')
        else:
            for criterion in QUAL_CRITERIA:
                processed[f'{criterion}_score'] = np.nan
            processed['meta_judge_reasoning'] = f"Error: {meta_error}" if meta_error else "Error: Missing parsed result"
            processed['meta_judge_analysis'] = ""
        individual_judges = record.get('judges', [])
        processed['num_judges_total'] = len(individual_judges)
        processed['judge_evaluations_list'] = []
        processed['num_judges_succeeded'] = 0
        processed['any_judge_error'] = False
        judge_scores_for_df = {}
        for judge_eval in individual_judges:
            judge_id = judge_eval.get('judge_id', 'unknown_judge')
            parsed = judge_eval.get('parsed_result')
            error = judge_eval.get('error')
            judge_info = {'judge_id': judge_id, 'error': error}
            if parsed and not error:
                judge_info.update(parsed)
                processed['judge_evaluations_list'].append(judge_info)
                processed['num_judges_succeeded'] += 1
                for crit in QUAL_CRITERIA:
                    judge_scores_for_df[f"{judge_id}_{crit}_score"] = parsed.get(crit)
            else:
                processed['judge_evaluations_list'].append(judge_info)
                processed['any_judge_error'] = True
                for crit in QUAL_CRITERIA:
                     judge_scores_for_df[f"{judge_id}_{crit}_score"] = np.nan
        processed.update(judge_scores_for_df)
        processed_records.append(processed)
    df = pd.DataFrame(processed_records)
    print(f"Preprocessing complete. Created DataFrame with {len(df)} rows.")
    return df

def compute_qualitative_metrics(df):
    """Computes and prints average qualitative consensus scores."""
    print("\n--- Qualitative Metrics (Meta-Judge Consensus Scores) ---")
    qual_cols = [f'{c}_score' for c in QUAL_CRITERIA]
    if not all(col in df.columns for col in qual_cols):
        print("Meta-judge score columns not found. Skipping analysis.")
        return
    qualitative_means = df.dropna(subset=qual_cols).groupby('generator_model_id')[qual_cols].mean()
    print("Average Scores (Mean per Generator Model):")
    if not qualitative_means.empty:
        print(qualitative_means.to_markdown(floatfmt=".3f"))
    else:
        print("No valid scores found to calculate means.")
    qualitative_std = df.dropna(subset=qual_cols).groupby('generator_model_id')[qual_cols].std()
    print("\nScore Consistency (Standard Deviation per Generator Model):")
    if not qualitative_std.empty:
        print(qualitative_std.to_markdown(floatfmt=".3f"))
    else:
        print("No valid scores found to calculate std dev.")

def analyze_inter_judge_agreement(df):
    """Analyzes agreement between individual judges using Kappa and Correlation."""
    print("\n--- Inter-Judge Agreement Analysis ---")

    if 'judge_evaluations_list' not in df.columns:
        print("'judge_evaluations_list' column not found. Ensure preprocessing ran correctly. Skipping.")
        return
    judge_records = []
    for index, row in df.iterrows():
        eval_list = row['judge_evaluations_list']
        if isinstance(eval_list, list):
            for judge_eval in eval_list:
                if not judge_eval.get('error') and all(c in judge_eval for c in QUAL_CRITERIA):
                    record = {'original_index': index}
                    record['judge_id'] = judge_eval.get('judge_id')
                    for crit in QUAL_CRITERIA:
                        record[crit] = judge_eval.get(crit)
                    judge_records.append(record)
    if not judge_records:
        print("No valid individual judge scores found to analyze agreement.")
        return
    judge_df = pd.DataFrame(judge_records)
    judge_ids = judge_df['judge_id'].unique()
    if len(judge_ids) < 2:
        print(f"Only found scores for {len(judge_ids)} judge(s). Need at least two to compare agreement. Skipping.")
        return
    print(f"Analyzing agreement between judges: {list(judge_ids)}")

    for crit in QUAL_CRITERIA:
        print(f"\nAgreement for: {crit}")
        pivot_df = judge_df.pivot(index='original_index', columns='judge_id', values=crit)
        pivot_df = pivot_df.dropna()
        if len(pivot_df) < 2:
             print(f"  Insufficient overlapping data points ({len(pivot_df)}) for {crit} agreement analysis.")
             continue
        print(f"  Cohen's Kappa (Pairwise):")
        kappa_scores = pd.DataFrame(index=judge_ids, columns=judge_ids, dtype=float)
        for i in range(len(judge_ids)):
            for j in range(i, len(judge_ids)):
                judge1 = judge_ids[i]
                judge2 = judge_ids[j]
                if judge1 == judge2:
                    kappa_scores.loc[judge1, judge2] = 1.0
                else:
                    if judge1 in pivot_df and judge2 in pivot_df:
                       kappa = cohen_kappa_score(pivot_df[judge1].round().astype(int), pivot_df[judge2].round().astype(int))
                       kappa_scores.loc[judge1, judge2] = kappa
                       kappa_scores.loc[judge2, judge1] = kappa
        print(kappa_scores.to_markdown(floatfmt=".3f"))
        print(f"\n  Pearson Correlation (Pairwise):")
        corr_matrix = pivot_df.corr(method='pearson')
        print(corr_matrix.to_markdown(floatfmt=".3f"))


def analyze_efficiency_and_errors(df):
    """Analyzes latency and error rates from the evaluation process."""
    print("\n--- Evaluation Efficiency and Robustness ---")
    agg_dict = {}
    if 'latency_seconds' in df.columns:
        agg_dict['avg_eval_latency_s'] = pd.NamedAgg(column='latency_seconds', aggfunc='mean')
    if 'meta_judge_error' in df.columns:
         agg_dict['meta_judge_fail_rate_%'] = pd.NamedAgg(column='meta_judge_error', aggfunc=lambda x: x.sum() / x.count() * 100)
    if 'any_judge_error' in df.columns:
         agg_dict['any_judge_fail_rate_%'] = pd.NamedAgg(column='any_judge_error', aggfunc=lambda x: x.sum() / x.count() * 100)
    if 'num_judges_succeeded' in df.columns and 'num_judges_total' in df.columns:
         df['judge_success_rate'] = df['num_judges_succeeded'] / df['num_judges_total']
         agg_dict['avg_judge_success_rate_%'] = pd.NamedAgg(column='judge_success_rate', aggfunc=lambda x: x.mean() * 100)
    if not agg_dict:
        print("No relevant columns found for efficiency/error analysis (latency_seconds, *_error). Skipping.")
        return
    efficiency_results = df.groupby('generator_model_id').agg(**agg_dict)

    print("Metrics per Generator Model Evaluated:")
    print(efficiency_results.to_markdown(floatfmt=".2f"))

def create_visualizations(df, output_dir='charts'):
    """Generates and saves charts based on the processed data."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Generating Charts (saving to '{output_path}/') ---")
    palette = sns.color_palette("viridis", n_colors=df['generator_model_id'].nunique())
    model_order = df['generator_model_id'].unique()
    qual_cols = [f'{c}_score' for c in QUAL_CRITERIA]
    if all(col in df.columns for col in qual_cols):
        qual_means = df.dropna(subset=qual_cols).groupby('generator_model_id')[qual_cols].mean()
        qual_means = qual_means.reset_index()
        qual_melted = qual_means.melt(id_vars='generator_model_id', var_name='Criterion', value_name='Average Score')
        plt.figure(figsize=(12, 7))
        sns.barplot(data=qual_melted, x='Criterion', y='Average Score', hue='generator_model_id', palette=palette, hue_order=model_order)
        plt.title('Average Qualitative Scores by Generator Model (Meta-Judge Consensus)')
        plt.ylabel(f'Average Score ({SCORE_MIN}-{SCORE_MAX})')
        plt.xlabel('Evaluation Criterion')
        plt.xticks(ticks=range(len(QUAL_CRITERIA)), labels=[c.replace('_score','').replace('_',' ').title() for c in qual_cols], rotation=0)
        plt.ylim(SCORE_MIN - 0.5, SCORE_MAX + 0.5)
        plt.legend(title='Generator Model', bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(output_path / 'qualitative_scores_bar_chart.png')
        print(f"Saved: qualitative_scores_bar_chart.png")
        plt.close()
    if 'latency_seconds' in df.columns:
        latency_means = df.groupby('generator_model_id')['latency_seconds'].mean().reindex(model_order)
        plt.figure(figsize=(10, 6))
        sns.barplot(x=latency_means.index, y=latency_means.values, palette=palette, order=model_order)
        plt.title('Average Multi-Judge Evaluation Latency per Review')
        plt.ylabel('Average Time (seconds)')
        plt.xlabel('Generator Model (whose review was evaluated)')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(output_path / 'evaluation_latency_bar_chart.png')
        print(f"Saved: evaluation_latency_bar_chart.png")
        plt.close()
    error_cols = [col for col in ['meta_judge_fail_rate_%', 'any_judge_fail_rate_%'] if col in df.columns]
    if error_cols:
        error_means = df.groupby('generator_model_id')[error_cols].mean().reindex(model_order)
        error_means = error_means.reset_index()
        error_melted = error_means.melt(id_vars='generator_model_id', var_name='Error Type', value_name='Failure Rate (%)')
        plt.figure(figsize=(10, 6))
        sns.barplot(data=error_melted, x='Error Type', y='Failure Rate (%)', hue='generator_model_id', palette=palette, hue_order=model_order)
        plt.title('Failure Rates During Multi-Judge Evaluation')
        plt.ylabel('Failure Rate (%)')
        plt.xlabel('Failure Point')
        plt.xticks(ticks=range(len(error_cols)), labels=[c.replace('_fail_rate_%','').replace('_',' ').title() for c in error_cols], rotation=0)
        plt.ylim(0, 105)
        plt.legend(title='Generator Model', bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(output_path / 'evaluation_error_rates_bar_chart.png')
        print(f"Saved: evaluation_error_rates_bar_chart.png")
        plt.close()

def main():
    parser = argparse.ArgumentParser(description="Analyze Multi-Judge Qualitative Evaluation Results.")
    parser.add_argument("--data-dir", default="data/evaluation_metrics/qualitative",
                        type=str, help="Path to the directory containing the qualitative evaluation JSON files.")
    parser.add_argument("--output-dir", default="charts",
                        type=str, help="Directory to save generated charts.")
    parser.add_argument("--no-charts", action="store_true", help="Skip generating and saving charts.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set logging level.")
    args = parser.parse_args()
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    log_format = '%(asctime)s - %(levelname)-8s - %(message)s'
    logging.basicConfig(level=log_level, format=log_format, handlers=[logging.StreamHandler()], force=True)
    input_path = Path(args.data_dir)
    output_path = Path(args.output_dir)
    if not input_path.is_dir():
        print(f"Error: Input data directory not found: {input_path}")
        return
    raw_eval_data = load_evaluation_files(input_path)
    if not raw_eval_data:
        print("No evaluation data loaded. Exiting.")
        return
    df = preprocess_data(raw_eval_data)
    if df.empty:
         print("Preprocessing resulted in an empty DataFrame. Exiting.")
         return
    compute_qualitative_metrics(df)
    analyze_inter_judge_agreement(df)
    analyze_efficiency_and_errors(df)
    if not args.no_charts:
        create_visualizations(df, output_dir=args.output_dir)
    print("\nAnalysis complete.")
if __name__ == "__main__":
    main()
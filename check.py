#!/usr/bin/env python3
"""
DATASET COMPOSITION CHECKER

Analyzes unified_dataset_clean.json to check:
1. How many samples from Defects4J vs GitHub
2. Sample distribution across both sources
3. Whether cleaning removed Defects4J data
4. Data quality per source
"""

import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

def analyze_dataset_composition():
    """Check Defects4J vs GitHub split in cleaned dataset"""
    
    dataset_path = Path('data/phase1_results/unified_dataset_clean.json')
    
    if not dataset_path.exists():
        print(f"❌ {dataset_path} not found")
        return
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        return
    
    if not isinstance(data, list):
        print(f"⚠ Data is {type(data).__name__}, not list")
        return
    
    print("="*80)
    print("DATASET COMPOSITION ANALYSIS")
    print("="*80)
    print(f"\nTotal samples: {len(data)}\n")
    
    # Count by source
    source_counts = defaultdict(int)
    source_samples = defaultdict(list)
    
    for item in data:
        source = item.get('source', 'unknown')
        source_counts[source] += 1
        source_samples[source].append(item)
    
    # ===================================================================
    # 1. SOURCE BREAKDOWN
    # ===================================================================
    print("="*80)
    print("1. SOURCE BREAKDOWN")
    print("="*80)
    
    for source, count in sorted(source_counts.items()):
        percentage = (count / len(data)) * 100
        print(f"\n{source.upper()}:")
        print(f"  Count:      {count}")
        print(f"  Percentage: {percentage:.1f}%")
        print(f"  Bar:        {'█' * int(percentage / 5)}")
    
    # ===================================================================
    # 2. DEFECTS4J ANALYSIS
    # ===================================================================
    print("\n" + "="*80)
    print("2. DEFECTS4J ANALYSIS")
    print("="*80)
    
    d4j_samples = source_samples.get('defects4j', [])
    if d4j_samples:
        print(f"\n✅ Defects4J found: {len(d4j_samples)} samples")
        
        # Projects
        projects = defaultdict(int)
        for sample in d4j_samples:
            project = sample.get('project', 'unknown')
            projects[project] += 1
        
        print("\nProjects:")
        for project, count in sorted(projects.items(), key=lambda x: x[1], reverse=True):
            print(f"  {project:.<30} {count:>3} samples")
        
        # Data quality check
        print("\nData Quality (% with code):")
        with_before = sum(1 for s in d4j_samples if s.get('code_before'))
        with_after = sum(1 for s in d4j_samples if s.get('code_after'))
        with_metadata = sum(1 for s in d4j_samples if s.get('metadata'))
        
        print(f"  code_before: {(with_before/len(d4j_samples)*100):>5.1f}%")
        print(f"  code_after:  {(with_after/len(d4j_samples)*100):>5.1f}%")
        print(f"  metadata:    {(with_metadata/len(d4j_samples)*100):>5.1f}%")
    else:
        print(f"\n❌ NO DEFECTS4J SAMPLES FOUND!")
        print("   ⚠️  This could be a problem for your evaluation!")
    
    # ===================================================================
    # 3. GITHUB ANALYSIS
    # ===================================================================
    print("\n" + "="*80)
    print("3. GITHUB ANALYSIS")
    print("="*80)
    
    github_samples = source_samples.get('github', [])
    if github_samples:
        print(f"\n✅ GitHub found: {len(github_samples)} samples")
        
        # Repositories
        repos = defaultdict(int)
        for sample in github_samples:
            project = sample.get('project', 'unknown')
            repos[project] += 1
        
        print(f"\nRepositories: {len(repos)} total")
        print("Top 10:")
        for repo, count in sorted(repos.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {repo:.<50} {count:>3} samples")
        
        # Data quality
        print("\nData Quality (% with code):")
        with_before = sum(1 for s in github_samples if s.get('code_before'))
        with_after = sum(1 for s in github_samples if s.get('code_after'))
        with_metadata = sum(1 for s in github_samples if s.get('metadata'))
        
        print(f"  code_before: {(with_before/len(github_samples)*100):>5.1f}%")
        print(f"  code_after:  {(with_after/len(github_samples)*100):>5.1f}%")
        print(f"  metadata:    {(with_metadata/len(github_samples)*100):>5.1f}%")
    else:
        print(f"\n⚠️  NO GITHUB SAMPLES FOUND!")
    
    # ===================================================================
    # 4. OTHER SOURCES
    # ===================================================================
    other_sources = {k: v for k, v in source_counts.items() 
                     if k not in ['defects4j', 'github']}
    if other_sources:
        print("\n" + "="*80)
        print("4. OTHER SOURCES")
        print("="*80)
        for source, count in other_sources.items():
            print(f"\n{source}: {count} samples")
    
    # ===================================================================
    # 5. SUMMARY TABLE
    # ===================================================================
    print("\n" + "="*80)
    print("5. SUMMARY TABLE")
    print("="*80)
    
    summary_data = []
    for source in ['defects4j', 'github'] + [s for s in source_counts.keys() 
                                              if s not in ['defects4j', 'github']]:
        if source in source_counts:
            samples = source_samples[source]
            count = len(samples)
            pct = (count / len(data)) * 100
            
            with_code = sum(1 for s in samples if s.get('code_before'))
            with_meta = sum(1 for s in samples if s.get('metadata'))
            
            summary_data.append({
                'Source': source.upper(),
                'Count': count,
                'Percentage': f"{pct:.1f}%",
                'With Code': f"{with_code/count*100:.0f}%",
                'With Metadata': f"{with_meta/count*100:.0f}%"
            })
    
    df_summary = pd.DataFrame(summary_data)
    print("\n" + df_summary.to_string(index=False))
    
    # ===================================================================
    # 6. RECOMMENDATIONS
    # ===================================================================
    print("\n" + "="*80)
    print("6. RECOMMENDATIONS")
    print("="*80)
    
    if len(d4j_samples) == 0:
        print("\n⚠️  CRITICAL ISSUE:")
        print("    No Defects4J samples in cleaned dataset!")
        print("    This means your evaluation will only have GitHub data.")
        print("\n    Potential causes:")
        print("    1. Cleaning script removed all Defects4J samples")
        print("    2. Defects4J data wasn't properly extracted initially")
        print("    3. Data format mismatch during cleaning")
        print("\n    RECOMMENDED ACTIONS:")
        print("    1. Check data/phase1_results/unified_dataset.json (before cleaning)")
        print("    2. Run: python3 check_original_dataset.py (see below)")
        print("    3. Review cleaning logic in dataset cleaning script")
        print("    4. Re-run extraction with debugging enabled")
    
    elif len(github_samples) == 0:
        print("\n⚠️  PARTIAL ISSUE:")
        print("    No GitHub samples in cleaned dataset!")
        print("    Evaluation will only use Defects4J data.")
    
    elif len(d4j_samples) < 50:
        print("\n⚠️  LOW DEFECTS4J COUNT:")
        print(f"    Only {len(d4j_samples)} Defects4J samples (should be 100+)")
        print("    Consider why so many were removed during cleaning")
    else:
        print("\n✅ BALANCED DISTRIBUTION:")
        print(f"    Defects4J: {len(d4j_samples)} ({len(d4j_samples)/len(data)*100:.0f}%)")
        print(f"    GitHub:    {len(github_samples)} ({len(github_samples)/len(data)*100:.0f}%)")
        print("    Good for comparative analysis!")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    analyze_dataset_composition()
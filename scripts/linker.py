#!/usr/bin/env python3
"""
DATASET LINKER - FIXED VERSION
Links unified_dataset.json to the format expected by generate_ai_reviews.py

This script extracts samples from unified_dataset.json and creates the 
expected directory structure SO AI reviews can find the data.
"""

import json
from pathlib import Path

def link_unified_to_legacy_format():
    """Convert unified dataset to legacy format expected by AI reviewer"""
    
    # Load unified dataset
    unified_file = Path('data/phase1_results/unified_dataset.json')
    if not unified_file.exists():
        print(f"❌ {unified_file} not found")
        return False
    
    with open(unified_file, 'r') as f:
        samples = json.load(f)
    
    print(f"✓ Loaded {len(samples)} samples from unified_dataset.json\n")
    
    # Create output directories
    defects4j_dir = Path('data/defects4j_bugs')
    github_dir = Path('data/github_prs')
    defects4j_dir.mkdir(parents=True, exist_ok=True)
    github_dir.mkdir(parents=True, exist_ok=True)
    
    defects4j_count = 0
    github_count = 0
    
    # Process each sample
    for sample in samples:
        source = sample.get('source', 'unknown')
        
        if source == 'defects4j':
            # Create defects4j metadata file
            sample_id = sample.get('id', 'unknown')
            metadata = {
                'bug_id': sample.get('id'),
                'source': 'defects4j',
                'project': sample.get('project'),
                'language': sample.get('language'),
                'metadata': sample.get('metadata', {}),
                'before_path': sample.get('before_path'),
                'after_path': sample.get('after_path'),
            }
            
            metadata_file = defects4j_dir / f"{sample_id}_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Save code files if present
            if sample.get('code_before'):
                code_file = defects4j_dir / f"{sample_id}_buggy.java"
                with open(code_file, 'w', encoding='utf-8') as f:
                    f.write(sample.get('code_before', ''))
            
            if sample.get('code_after'):
                code_file = defects4j_dir / f"{sample_id}_fixed.java"
                with open(code_file, 'w', encoding='utf-8') as f:
                    f.write(sample.get('code_after', ''))
            
            defects4j_count += 1
            print(f"✓ Defects4J: {sample_id}")
        
        elif source == 'github':
            # Create github PR metadata file
            sample_id = sample.get('id', 'unknown')
            repo = sample.get('project', 'unknown')
            
            # Create repo directory
            repo_dir = github_dir / repo.replace('/', '_')
            repo_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract files_info if it exists in metadata
            files_info = sample.get('metadata', {}).get('files_info', {})
            
            metadata = {
                'id': sample_id,
                'source': 'github',
                'repository': repo,
                'language': sample.get('language'),
                'metadata': sample.get('metadata', {}),
                'files_changed': [],  # Placeholder
            }
            
            metadata_file = repo_dir / f"{sample_id}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Save code patches as BEFORE files
            # The unified dataset stores patches, so we'll save them as BEFORE
            if isinstance(files_info, dict) and 'files' in files_info:
                for filename, file_data in files_info.get('files', {}).items():
                    if isinstance(file_data, dict):
                        patch_content = file_data.get('patch', '')
                        if patch_content:
                            # Save patch as BEFORE file
                            safe_filename = filename.replace('/', '_').replace('.', '_')
                            before_file = repo_dir / f"BEFORE_{safe_filename}.patch"
                            with open(before_file, 'w', encoding='utf-8') as f:
                                f.write(patch_content)
            
            github_count += 1
            print(f"✓ GitHub: {sample_id}")
    
    print(f"\n{'='*60}")
    print(f"LINKING COMPLETE")
    print(f"{'='*60}")
    print(f"Defects4J samples: {defects4j_count}")
    print(f"GitHub samples: {github_count}")
    print(f"Total: {defects4j_count + github_count}")
    print(f"\n✓ Data linked to:")
    print(f"  - {defects4j_dir}")
    print(f"  - {github_dir}")
    print(f"\nNow run: python3 generate_ai_reviews.py")
    
    return True

if __name__ == '__main__':
    link_unified_to_legacy_format()
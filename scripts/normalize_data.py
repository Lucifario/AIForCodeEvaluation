import json
import logging
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def normalize():
    input_path = Path('data/phase1_results/unified_dataset.json')
    output_path = Path('data/phase1_results/unified_dataset_clean.json')
    
    if not input_path.exists():
        print(f"❌ Cannot find {input_path}")
        return

    print(f"📖 Reading {input_path}...")
    with open(input_path, 'r') as f:
        data = json.load(f)

    normalized_data = []
    success_count = 0
    
    print(f"🔍 Normalizing {len(data)} samples...")

    for item in data:
        new_item = item.copy()
        source = item.get('source')
        valid_path = None

        # 1. FIND THE PATH
        # Strategy A: GitHub format
        if 'source_files_path' in item:
            p = Path(item['source_files_path'])
            if not p.exists(): # Try relative to data root
                 p = Path('data') / 'github_prs_aggressive' / p.name
            if p.exists(): valid_path = p

        # Strategy B: Defects4J format
        if not valid_path and 'source_files' in item and 'directory' in item['source_files']:
            p = Path(item['source_files']['directory'])
            if not p.exists(): # Try relative
                 p = Path('data') / 'defects4j_aggressive' / p.name
            if p.exists(): valid_path = p

        # 2. VALIDATE CODE EXISTS
        if valid_path:
            # Look for the actual code file inside
            code_files = list(valid_path.glob('*.java')) + list(valid_path.glob('*.py')) + list(valid_path.glob('BEFORE_*'))
            
            if code_files:
                # Found it! Standardize the entry.
                new_item['source_files_path'] = str(valid_path)
                # Simplify: Remove nested complex keys if present
                if 'source_files' in new_item: del new_item['source_files'] 
                
                normalized_data.append(new_item)
                success_count += 1
            else:
                print(f"⚠️  Found dir but NO code files: {valid_path}")
        else:
            # If we can't find the path, we skip this item to keep dataset clean
            pass

    # Save the clean dataset
    with open(output_path, 'w') as f:
        json.dump(normalized_data, f, indent=2)

    print("\n" + "="*40)
    print(f"✅ Normalization Complete")
    print(f"Original: {len(data)}")
    print(f"Cleaned:  {success_count}")
    print(f"Saved to: {output_path}")
    print("="*40)
    print("👉 Now update your config.yaml to use 'unified_dataset_clean.json'")

if __name__ == "__main__":
    normalize()
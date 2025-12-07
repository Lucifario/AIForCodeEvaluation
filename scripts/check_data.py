import json
import sys
from pathlib import Path

def check_dataset():
    dataset_path = Path('data/phase1_results/unified_dataset.json')
    if not dataset_path.exists():
        print(f"❌ Dataset not found at {dataset_path}")
        return

    with open(dataset_path, 'r') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} samples from dataset.")
    
    success_count = 0
    fail_count = 0
    
    # Check first 20 samples to debug
    print("\n--- Checking first 20 samples ---")
    for item in data[:20]:
        path_str = item.get('source_files_path')
        if not path_str:
            print(f"❌ Item {item['id']} has no source_files_path")
            fail_count += 1
            continue
            
        path = Path(path_str)
        if not path.exists():
            # Try relative to root
            path = Path.cwd() / path_str
        
        if not path.exists():
            print(f"❌ Path missing: {path}")
            fail_count += 1
        else:
            # Check for files inside
            files = list(path.glob('*'))
            code_files = [f.name for f in files if f.suffix in ['.java', '.py']]
            if code_files:
                print(f"✅ Found {len(code_files)} code files in {item['id']}: {code_files[:1]}...")
                success_count += 1
            else:
                print(f"⚠️ Directory empty or no code files: {path}")
                print(f"   Contents: {[f.name for f in files]}")
                fail_count += 1

    print(f"\n--- Summary ---")
    print(f"Verified Accessible Code: {success_count}")
    print(f"Missing/Empty: {fail_count}")

if __name__ == "__main__":
    check_dataset()
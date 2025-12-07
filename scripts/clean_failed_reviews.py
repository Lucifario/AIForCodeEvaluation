import json
import os
from pathlib import Path

def clean():
    reviews_dir = Path('data/ai_reviews')
    deleted = 0
    kept = 0
    
    print(f"Scanning {reviews_dir}...")
    for f in reviews_dir.glob('*.json'):
        try:
            with open(f, 'r') as file:
                data = json.load(file)
            
            # Check for signs of failure
            is_failed = False
            
            # 1. Explicit error field
            if data.get('error') or data.get('review', {}).get('error'):
                is_failed = True
                
            # 2. Empty response
            review_content = data.get('review', {})
            if isinstance(review_content, dict):
                if not review_content.get('response') and not data.get('parsed_llm_output'):
                    is_failed = True
            
            # 3. "Rate limit" or "Payment" text in content
            raw_text = str(data)
            if "Payment Required" in raw_text or "Rate limit reached" in raw_text:
                is_failed = True

            if is_failed:
                print(f"Deleting failed review: {f.name}")
                os.remove(f)
                deleted += 1
            else:
                kept += 1
                
        except Exception as e:
            print(f"Deleting corrupted file: {f.name}")
            os.remove(f)
            deleted += 1

    print(f"\nSummary: Deleted {deleted} failed files. Kept {kept} valid files.")

if __name__ == '__main__':
    clean()
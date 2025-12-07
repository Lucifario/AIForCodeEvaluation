#!/usr/bin/env python3
"""
Extract Human Reviews as Baseline for Evaluation

Treats human/expert reviews from the dataset as a "model" so judges can evaluate them too.
This enables direct comparison: Human Expert vs. AI Models vs. Qodo.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_human_reviews():
    """Extract human reviews from unified_dataset_clean.json and save as review files"""
    
    dataset_path = Path('data/phase1_results/unified_dataset_clean.json')
    output_dir = Path('data/ai_reviews')
    
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return False
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return False
    
    count = 0
    skipped = 0
    
    for item in dataset:
        try:
            sample_id = item.get('id', 'unknown')
            source = item.get('source', 'unknown')
            
            # Extract human review - structure depends on source
            human_comments = []
            code_context = ""
            
            if source == 'github':
                # GitHub PRs have reviewer comments in metadata
                metadata = item.get('metadata', {})
                pr_data = metadata.get('PR_DATA', {})
                
                # Collect review comments
                review_comments = pr_data.get('review_comments', [])
                if isinstance(review_comments, list):
                    for comment in review_comments:
                        if isinstance(comment, dict):
                            body = comment.get('body', '')
                            if body:
                                human_comments.append(body)
                
                # Get code context from file content
                code_before = item.get('code_before', '')
                if code_before:
                    code_context = code_before[:3000]  # Limit to 3000 chars
                    
            elif source == 'defects4j':
                # Defects4J has bug description and fix explanation
                metadata = item.get('metadata', {})
                bug_desc = metadata.get('bug_description', '')
                fix_expl = metadata.get('fix_explanation', '')
                
                if bug_desc:
                    human_comments.append(f"Bug Description: {bug_desc}")
                if fix_expl:
                    human_comments.append(f"Fix Explanation: {fix_expl}")
                
                code_context = item.get('code_before', '')[:3000]
            
            # Skip if no human comments found
            if not human_comments:
                skipped += 1
                continue
            
            # Aggregate all comments into one review text
            full_review = "Human Expert Review:\n" + "\n---\n".join(human_comments)
            
            # Save as a "review file" matching LLM output structure
            output_file = output_dir / f"{sample_id}_review_human_expert.json"
            
            review_data = {
                "sample_id": sample_id,
                "model_id": "human_expert",
                "source": source,
                "code_context": code_context,
                "review": {
                    "response": full_review
                },
                "timestamp": datetime.now().isoformat(),
                "is_human": True
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(review_data, f, indent=2, ensure_ascii=False)
            
            count += 1
            logger.info(f"✓ Extracted human review: {sample_id} ({source})")
            
        except Exception as e:
            logger.warning(f"Failed to process {item.get('id', 'unknown')}: {e}")
            skipped += 1
            continue
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Human Review Extraction Complete")
    logger.info(f"{'='*60}")
    logger.info(f"Extracted: {count} human reviews")
    logger.info(f"Skipped:   {skipped} (no human data)")
    logger.info(f"Total:     {count + skipped}")
    logger.info(f"\nNext step: Run multi-judge evaluation on all reviews including human_expert")
    
    return True

if __name__ == '__main__':
    success = extract_human_reviews()
    exit(0 if success else 1)
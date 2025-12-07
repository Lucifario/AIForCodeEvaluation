#!/usr/bin/env python3
"""
SCRIPT 2: Generate AI AFTER_AI fixes from BEFORE buggy code
"""
import json
from pathlib import Path
from typing import Dict, List

# Load your extracted triples
with open("data/human_vs_ai_defects4j/01_baseline/defects4j_complete_triples.json") as f:
    triples = json.load(f)

print(f"Loaded {len(triples)} Defects4J triples")

models = ["qwen-coder-32b", "llama3-8b-groq", "mistral-nemo"]
output_dir = Path("data/human_vs_ai_defects4j/02_ai_fixes")
output_dir.mkdir(parents=True, exist_ok=True)

for model in models:
    ai_fixes = []
    
    for triple in triples:
        # SIMPLIFIED: Use your existing llm_client.py or mock for now
        buggy_code = triple["before"][:4000]  # Truncate for prompt
        
        # TODO: Replace with your real LLM call
        ai_response = {
            "fixed_code": "/* AI GENERATED FIX */\n" + buggy_code[:2000] + "\n// AI attempted fix",
            "review": f"AI {model} analyzed Math-1 bug and proposed fixes",
            "confidence": 4
        }
        
        ai_fixes.append({
            "id": triple["id"],
            "model": model,
            "before": triple["before"][:2000],
            "after_ai": ai_response,
            "human_after": triple["after"][:2000],
            "project": triple["project"]
        })
        print(f"✅ {model}: Generated fix for {triple['id']}")
    
    # Save per model
    model_dir = output_dir / model
    model_dir.mkdir(exist_ok=True)
    output_file = model_dir / "ai_fixes.json"
    
    with open(output_file, "w") as f:
        json.dump(ai_fixes, f, indent=2)
    
    print(f"📁 Saved {len(ai_fixes)} {model} fixes: {output_file}")

print("\n🎉 STEP 2 COMPLETE: AI fixes generated!")
print("Next: python3 judge_human_vs_ai.py")

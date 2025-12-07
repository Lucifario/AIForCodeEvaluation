#!/usr/bin/env python3
"""
✅ FINAL FIXED: Extract REAL Defects4J (BEFORE + HUMAN AFTER)
"""
import json
from pathlib import Path
from pathlib import Path

def extract_real_defects4j_final():
    triples = []
    
    # Search buggy/fixed checkouts inside defects4j folder
    search_base = Path("./defects4j")
    all_dirs = list(search_base.glob("*bug*")) + list(search_base.glob("*_f*")) + list(search_base.glob("*fixed*"))
    
    print(f"🔍 Found {len(all_dirs)} checkout directories:")
    for d in all_dirs:
        print(f"  - {d.name}")
    
    # Rest of script remains same...    
    buggy_dirs = [d for d in all_dirs if any(x in d.name.lower() for x in ['bug', 'b_'])]
    fixed_dirs = [d for d in all_dirs if any(x in d.name.lower() for x in ['f_', 'fixed'])]
    
    print(f"\n🔍 Buggy: {len(buggy_dirs)}, Fixed: {len(fixed_dirs)}")
    
    for buggy_dir in buggy_dirs:
        if buggy_dir.is_dir():
            java_files = list(buggy_dir.rglob("*.java"))
            if java_files:
                main_file = java_files[0]
                sample_id = buggy_dir.name
                
                # Find matching fixed version
                fixed_match = None
                for fixed_dir in fixed_dirs:
                    if ('f' in fixed_dir.name and 'b' in buggy_dir.name and 
                        buggy_dir.name.replace('b', 'f') in fixed_dir.name):
                        fixed_match = fixed_dir
                        break
                
                after_code = "HUMAN_FIXED_VERSION_FOUND"
                if fixed_match and list(fixed_match.rglob("*.java")):
                    after_file = list(fixed_match.rglob("*.java"))[0]
                    after_code = after_file.read_text(errors="ignore")[:8000]
                else:
                    after_code = "NO_FIXED_VERSION_YET"
                
                triples.append({
                    "id": sample_id,
                    "source": "defects4j",
                    "before": main_file.read_text(errors="ignore")[:8000],  # BUGGY
                    "after": after_code,                                       # HUMAN FIXED
                    "buggy_dir": str(buggy_dir),
                    "fixed_dir": str(fixed_match) if fixed_match else None,
                    "project": buggy_dir.name.split("_")[0],
                    "java_files_count": len(java_files)
                })
                print(f"✅ {sample_id}: {len(java_files)} files")
    
    # Save COMPLETE dataset
    output_dir = Path("data/human_vs_ai_defects4j/01_baseline")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "defects4j_complete_triples.json"
    with open(output_file, "w") as f:
        json.dump(triples, f, indent=2)
    
    print(f"\n🎉 EXTRACTED {len(triples)} COMPLETE DEFECTS4J TRIPLES!")
    print(f"📁 Saved: {output_file}")
    return triples

if __name__ == "__main__":
    extract_real_defects4j_final()

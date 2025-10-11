#!/usr/bin/env python3
"""
Debug script to check lexicon system status
"""

import json
from pathlib import Path

def check_lexicon_system():
    """Check the current state of the lexicon system"""
    print("=" * 50)
    print("LEXICON SYSTEM DEBUG")
    print("=" * 50)
    
    # Check lexicon files
    print("\n1. Checking lexicon files...")
    
    auto_corrections_path = Path("data/lexicons/auto_corrections.json")
    frequency_path = Path("data/lexicons/correction_frequency.json")
    config_path = Path("config.json")
    
    if auto_corrections_path.exists():
        with auto_corrections_path.open("r", encoding="utf-8") as f:
            auto_corrections = json.load(f)
        print(f"[OK] Auto-corrections lexicon: {len(auto_corrections)} patterns")
        for original, corrected in list(auto_corrections.items())[:3]:
            print(f"     '{original}' -> '{corrected}'")
        if len(auto_corrections) > 3:
            print(f"     ... and {len(auto_corrections) - 3} more")
    else:
        print("[MISSING] Auto-corrections lexicon")
    
    if frequency_path.exists():
        with frequency_path.open("r", encoding="utf-8") as f:
            frequency_data = json.load(f)
        print(f"[OK] Frequency data: {len(frequency_data)} patterns")
        for pattern, count in list(frequency_data.items())[:3]:
            print(f"     {pattern} (count: {count})")
    else:
        print("[MISSING] Frequency data")
    
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        threshold = config.get("lexicon_learning_threshold", "NOT SET")
        print(f"[OK] Config file - Learning threshold: {threshold}")
    else:
        print("[MISSING] Config file")
    
    # Check correction logs
    print("\n2. Checking correction logs...")
    corrections_dir = Path("data/logs/corrections")
    if corrections_dir.exists():
        correction_files = list(corrections_dir.glob("*.json"))
        print(f"[OK] Correction logs: {len(correction_files)} documents")
        
        total_corrections = 0
        for file_path in correction_files[:3]:  # Check first 3 files
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                corrections = data.get("corrections", [])
                total_corrections += len(corrections)
                print(f"     {file_path.name}: {len(corrections)} corrections")
        
        print(f"Total corrections across all documents: {total_corrections}")
    else:
        print("[MISSING] Correction logs directory")
    
    # Check if patterns should have been learned
    print("\n3. Analysis...")
    if auto_corrections_path.exists() and frequency_path.exists():
        with auto_corrections_path.open("r", encoding="utf-8") as f:
            auto_corrections = json.load(f)
        with frequency_path.open("r", encoding="utf-8") as f:
            frequency_data = json.load(f)
        
        # Check which patterns have high frequency but aren't in lexicon
        high_frequency_patterns = {k: v for k, v in frequency_data.items() if v >= 1}
        print(f"Patterns with frequency >= 1: {len(high_frequency_patterns)}")
        
        for pattern, count in high_frequency_patterns.items():
            if " -> " in pattern:
                original = pattern.split(" -> ")[0]
                if original not in auto_corrections:
                    print(f"     SHOULD BE LEARNED: {pattern} (count: {count})")
                else:
                    print(f"     ALREADY LEARNED: {pattern} (count: {count})")
    
    print("\n4. Recommendations...")
    print("To test lexicon learning:")
    print("1. Upload a document")
    print("2. Make a correction (e.g., fix 'LDAUTPA12345673<<<<<<' to 'LDAUTPA12345673<<<<<<<')")
    print("3. Upload another document with the same error")
    print("4. Check if it's auto-corrected (green box instead of red)")
    print("\nIf auto-correction isn't working:")
    print("- Restart the server to load new lexicon processor code")
    print("- Check server logs for lexicon application messages")

if __name__ == "__main__":
    check_lexicon_system()

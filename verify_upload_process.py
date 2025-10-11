#!/usr/bin/env python3
"""
Verify the upload process and lexicon application
"""

import json
import requests
from pathlib import Path

def verify_lexicon_in_upload():
    """Verify that lexicon corrections are applied during upload"""
    print("VERIFYING UPLOAD PROCESS")
    print("=" * 40)
    
    # 1. Check current lexicon
    lexicon_path = Path("data/lexicons/auto_corrections.json")
    if lexicon_path.exists():
        with lexicon_path.open("r", encoding="utf-8") as f:
            lexicon = json.load(f)
        
        print(f"✓ Lexicon loaded: {len(lexicon)} patterns")
        for original, corrected in list(lexicon.items())[:3]:
            print(f"  '{original}' -> '{corrected}'")
        
        # Test specific pattern
        test_original = "ZAIDI<<NOUR<EDDINE<<<<<<<<<<" 
        if test_original in lexicon:
            print(f"\n✓ Target pattern found in lexicon:")
            print(f"  '{test_original}' -> '{lexicon[test_original]}'")
        else:
            print(f"\n✗ Target pattern NOT found in lexicon")
            print(f"  Looking for: '{test_original}'")
            print(f"  Available patterns:")
            for k in lexicon.keys():
                if "ZAIDI" in k:
                    print(f"    '{k}'")
        
    else:
        print("✗ No lexicon file found")
        return
    
    # 2. Check server status
    try:
        response = requests.get("http://localhost:8000/api/config", timeout=5)
        if response.ok:
            config = response.json()
            print(f"\n✓ Server responding")
            print(f"  Learning threshold: {config.get('lexicon_learning_threshold', 'N/A')}")
            print(f"  Auto-correction enabled: {config.get('auto_correction_enabled', 'N/A')}")
        else:
            print(f"\n✗ Server config API not working: {response.status_code}")
    except:
        print(f"\n✗ Server not responding or config API not available")
    
    # 3. Check if we can test with existing documents
    outputs_dir = Path("data/outputs")
    if outputs_dir.exists():
        json_files = list(outputs_dir.glob("*.json"))
        json_files = [f for f in json_files if not any(suffix in f.name for suffix in ['_raw', '_extracted', '_layout', '_quality'])]
        
        if json_files:
            # Check a recent document
            latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
            print(f"\n✓ Found recent document: {latest_file.name}")
            
            with latest_file.open("r", encoding="utf-8") as f:
                ocr_data = json.load(f)
            
            # Check if any words were auto-corrected
            auto_corrected_count = 0
            total_words = 0
            sample_words = []
            
            for page in ocr_data.get("pages", []):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        for word in line.get("words", []):
                            total_words += 1
                            if word.get("auto_corrected") or word.get("corrected_by_lexicon"):
                                auto_corrected_count += 1
                            
                            # Collect sample words
                            if len(sample_words) < 5:
                                sample_words.append({
                                    "value": word.get("value", ""),
                                    "auto_corrected": word.get("auto_corrected", False),
                                    "original_value": word.get("original_value", "")
                                })
            
            print(f"  Total words: {total_words}")
            print(f"  Auto-corrected words: {auto_corrected_count}")
            
            if auto_corrected_count > 0:
                print(f"  ✓ Auto-corrections ARE being applied!")
            else:
                print(f"  ✗ No auto-corrections found in recent document")
                print(f"  Sample words:")
                for word in sample_words:
                    print(f"    '{word['value']}' (auto_corrected: {word['auto_corrected']})")

def main():
    verify_lexicon_in_upload()
    
    print(f"\n" + "=" * 40)
    print("TROUBLESHOOTING STEPS:")
    print("1. Upload a document with known errors")
    print("2. Check server console for lexicon messages")
    print("3. Look for green bounding boxes (auto-corrected)")
    print("4. If no auto-corrections, check server logs")

if __name__ == "__main__":
    main()

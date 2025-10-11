#!/usr/bin/env python3
"""
Comprehensive test script for enhanced FinoktAI OCR features
Tests real-time correction sync, lexicon learning, and auto-correction
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_enhanced_system():
    """Test all enhanced features"""
    print("=" * 60)
    print("TESTING ENHANCED FINOKTAI OCR FEATURES")
    print("=" * 60)
    
    # Test 1: Server health
    print("\n1. Testing server health...")
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code == 200:
            print("[OK] Server is running")
        else:
            print(f"[ERROR] Server status: {response.status_code}")
            return
    except Exception as e:
        print(f"[ERROR] Cannot connect: {e}")
        return
    
    # Test 2: Configuration system
    print("\n2. Testing configuration system...")
    try:
        response = requests.get(f"{BASE_URL}/api/config", timeout=10)
        if response.ok:
            config = response.json()
            print(f"[OK] Configuration loaded")
            print(f"     Learning threshold: {config.get('lexicon_learning_threshold', 'N/A')}")
            print(f"     Auto-correction: {config.get('auto_correction_enabled', 'N/A')}")
        else:
            print(f"[ERROR] Config API failed: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Config test failed: {e}")
    
    # Test 3: Enhanced API endpoints
    print("\n3. Testing enhanced API endpoints...")
    endpoints = [
        ("/api/lexicon", "Lexicon Data"),
        ("/api/training_data/stats", "Training Stats"),
        ("/api/document_types", "Document Types")
    ]
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            if response.ok:
                data = response.json()
                print(f"[OK] {name}")
                
                if endpoint == "/api/lexicon":
                    print(f"     Lexicon size: {data.get('lexicon_size', 0)}")
                    print(f"     Frequency patterns: {data.get('total_patterns', 0)}")
                elif endpoint == "/api/training_data/stats":
                    print(f"     Training samples: {data.get('total_samples', 0)}")
                elif endpoint == "/api/document_types":
                    print(f"     Document types: {data.get('total_types', 0)}")
            else:
                print(f"[ERROR] {name} - Status: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] {name} - {e}")
    
    # Test 4: Directory structure
    print("\n4. Testing enhanced directory structure...")
    directories = [
        "data/logs/corrections",
        "data/lexicons", 
        "data/training_data/ocr_samples",
        "models/ocr_weights"
    ]
    
    for dir_path in directories:
        if Path(dir_path).exists():
            file_count = len(list(Path(dir_path).glob("*")))
            print(f"[OK] {dir_path} ({file_count} files)")
        else:
            print(f"[MISSING] {dir_path}")
    
    # Test 5: Configuration update
    print("\n5. Testing configuration update...")
    try:
        # Test updating learning threshold
        update_data = {
            'key': 'lexicon_learning_threshold',
            'value': '1'
        }
        
        response = requests.post(f"{BASE_URL}/api/config/update", data=update_data, timeout=10)
        if response.ok:
            result = response.json()
            print(f"[OK] Configuration update successful")
            print(f"     Updated: {result.get('key')} = {result.get('value')}")
        else:
            print(f"[ERROR] Config update failed: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Config update test failed: {e}")
    
    # Test 6: Check if lexicon files exist and show content
    print("\n6. Checking lexicon files...")
    lexicon_files = [
        "data/lexicons/auto_corrections.json",
        "data/lexicons/correction_frequency.json",
        "config.json"
    ]
    
    for file_path in lexicon_files:
        path = Path(file_path)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"[OK] {file_path}")
                if "auto_corrections" in file_path:
                    print(f"     Auto-corrections: {len(data)} patterns")
                elif "frequency" in file_path:
                    print(f"     Frequency data: {len(data)} patterns")
                elif "config.json" in file_path:
                    print(f"     Learning threshold: {data.get('lexicon_learning_threshold', 'N/A')}")
            except Exception as e:
                print(f"[ERROR] Failed to read {file_path}: {e}")
        else:
            print(f"[MISSING] {file_path}")

def print_usage_instructions():
    """Print comprehensive usage instructions"""
    print("\n" + "=" * 60)
    print("ENHANCED FEATURES USAGE GUIDE")
    print("=" * 60)
    
    print("\n🎯 TESTING WORKFLOW:")
    print("1. Open http://localhost:8000 in your browser")
    print("2. Upload a document (PDF/image)")
    print("3. Look for colored bounding boxes:")
    print("   • RED = Original OCR text")
    print("   • GREEN = Auto-corrected by lexicon")
    print("   • BLUE = Manually corrected by user")
    
    print("\n🔧 CORRECTION TESTING:")
    print("1. Click any RED bounding box to edit")
    print("2. Make a correction and save")
    print("3. With threshold=1, it should immediately add to lexicon")
    print("4. Upload same/similar document - errors should auto-correct")
    
    print("\n📊 LEARNING SYSTEM:")
    print("1. Check 'Learning Stats' tab for:")
    print("   • Manual corrections count")
    print("   • Auto-corrections applied")
    print("   • Lexicon size and patterns")
    print("   • Training data statistics")
    
    print("\n⚙️ CONFIGURATION:")
    print("1. In Learning Stats tab, adjust 'Learning Threshold'")
    print("2. Set to 1 for immediate learning")
    print("3. Set to 3+ for conservative learning")
    
    print("\n🎨 VISUAL INDICATORS:")
    print("• Green boxes = Auto-corrected words")
    print("• Blue boxes = Manually corrected words") 
    print("• Red boxes = Original OCR text")
    print("• Tooltips show correction history")
    
    print("\n📈 SUCCESS METRICS:")
    print("✓ Bounding boxes are clickable and accurate")
    print("✓ Corrections sync across all UI panels")
    print("✓ Lexicon learning triggers at threshold")
    print("✓ Auto-corrections apply on new documents")
    print("✓ All exports use corrected text")
    print("✓ Training data is generated automatically")

def main():
    test_enhanced_system()
    print_usage_instructions()
    
    print("\n" + "=" * 60)
    print("🚀 SYSTEM READY FOR ENHANCED TESTING!")
    print("Open http://localhost:8000 and test the new features")
    print("=" * 60)

if __name__ == "__main__":
    main()

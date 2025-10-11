#!/usr/bin/env python3
"""
Debug correction saving process
"""

import requests
import json

def test_save_correction():
    """Test the save correction endpoint directly"""
    print("Testing correction save endpoint...")
    
    # Test data
    test_data = {
        'doc_id': 'test_doc_123',
        'page': 0,
        'word_id': 'p0_w1', 
        'original_text': 'TEST_ORIGINAL',
        'corrected_text': 'TEST_CORRECTED',
        'corrected_bbox': '[[0.1, 0.1], [0.2, 0.2]]',
        'user_id': 'test_user'
    }
    
    try:
        response = requests.post('http://localhost:8000/save_correction', data=test_data, timeout=10)
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        
        if response.ok:
            result = response.json()
            print("SUCCESS: Correction saved")
            print(f"Result: {result}")
        else:
            print("ERROR: Correction save failed")
            
    except Exception as e:
        print(f"ERROR: {e}")

def test_lexicon_endpoint():
    """Test lexicon endpoint"""
    print("\nTesting lexicon endpoint...")
    
    try:
        response = requests.get('http://localhost:8000/api/lexicon', timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print("SUCCESS: Lexicon data retrieved")
            print(f"Lexicon size: {data.get('lexicon_size', 0)}")
            print(f"Total patterns: {data.get('total_patterns', 0)}")
            
            # Show first few patterns
            lexicon = data.get('lexicon', {})
            for i, (original, corrected) in enumerate(list(lexicon.items())[:3]):
                print(f"  Pattern {i+1}: '{original}' -> '{corrected}'")
        else:
            print("ERROR: Lexicon endpoint failed")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"ERROR: {e}")

def main():
    print("=" * 50)
    print("DEBUGGING CORRECTION SAVE SYSTEM")
    print("=" * 50)
    
    test_save_correction()
    test_lexicon_endpoint()
    
    print("\n" + "=" * 50)
    print("If correction saving works:")
    print("1. Check data/logs/corrections/ for new files")
    print("2. Check data/lexicons/ for updated patterns")
    print("3. Try making corrections in the UI")

if __name__ == "__main__":
    main()

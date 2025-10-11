#!/usr/bin/env python3
"""
Simple system test for FinoktAI OCR Enhanced Features
"""

import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_server():
    """Test if server is running"""
    print("Testing server health...")
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code == 200:
            print("[OK] Server is running")
            return True
        else:
            print(f"[ERROR] Server status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[ERROR] Cannot connect to server")
        print("Make sure server is running: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        return False

def test_apis():
    """Test API endpoints"""
    print("\nTesting API endpoints...")
    
    endpoints = {
        "/api/document_types": "Document Types",
        "/api/lexicon": "Lexicon Data", 
        "/api/training_data/stats": "Training Stats"
    }
    
    for endpoint, name in endpoints.items():
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"[OK] {name}")
                if endpoint == "/api/document_types":
                    print(f"     Available types: {data.get('total_types', 0)}")
                elif endpoint == "/api/lexicon":
                    print(f"     Lexicon size: {data.get('lexicon_size', 0)}")
                elif endpoint == "/api/training_data/stats":
                    print(f"     Training samples: {data.get('total_samples', 0)}")
            else:
                print(f"[ERROR] {name} - Status: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] {name} - {e}")

def check_directories():
    """Check required directories"""
    print("\nChecking directories...")
    
    dirs = [
        "data/logs/corrections",
        "data/lexicons",
        "data/training_data/ocr_samples",
        "models/ocr_weights"
    ]
    
    for dir_path in dirs:
        if Path(dir_path).exists():
            print(f"[OK] {dir_path}")
        else:
            print(f"[MISSING] {dir_path}")

def main():
    print("=" * 50)
    print("FinoktAI OCR System Test")
    print("=" * 50)
    
    if not test_server():
        return
    
    test_apis()
    check_directories()
    
    print("\n" + "=" * 50)
    print("TESTING INSTRUCTIONS:")
    print("1. Open http://localhost:8000 in your browser")
    print("2. Upload a document (PDF or image)")
    print("3. Click red bounding boxes to edit text")
    print("4. Check 'Learning Stats' tab for analytics")
    print("5. Make same correction 3 times to trigger learning")
    print("=" * 50)

if __name__ == "__main__":
    main()

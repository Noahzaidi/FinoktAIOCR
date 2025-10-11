#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick system test script for FinoktAI OCR Enhanced Features
Run this after starting the server to verify basic functionality
"""

import requests
import json
import time
import os
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Server configuration
BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30

def test_server_health():
    """Test if server is running and responsive"""
    print("[*] Testing server health...")
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code == 200:
            print("[+] Server is running and responsive")
            return True
        else:
            print(f"[-] Server returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[-] Cannot connect to server. Make sure it's running on localhost:8000")
        return False
    except Exception as e:
        print(f"[-] Server health check failed: {e}")
        return False

def test_api_endpoints():
    """Test key API endpoints"""
    print("\n[*] Testing API endpoints...")
    
    endpoints = [
        "/api/document_types",
        "/api/lexicon", 
        "/api/training_data/stats"
    ]
    
    results = {}
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            if response.status_code == 200:
                print(f"[+] {endpoint} - OK")
                results[endpoint] = response.json()
            else:
                print(f"[-] {endpoint} - Status: {response.status_code}")
                results[endpoint] = None
        except Exception as e:
            print(f"[-] {endpoint} - Error: {e}")
            results[endpoint] = None
    
    return results

def test_file_structure():
    """Test if required directories exist"""
    print("\n🔍 Testing file structure...")
    
    required_dirs = [
        "data/logs/corrections",
        "data/lexicons", 
        "data/training_data/ocr_samples",
        "models/ocr_weights"
    ]
    
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"✅ {dir_path} - Exists")
        else:
            print(f"❌ {dir_path} - Missing")

def test_sample_documents():
    """Check if sample documents are available for testing"""
    print("\n🔍 Checking for sample documents...")
    
    upload_dir = Path("data/uploads")
    if upload_dir.exists():
        files = list(upload_dir.glob("*"))
        print(f"📁 Found {len(files)} files in uploads directory")
        
        # Show first few files as examples
        for i, file_path in enumerate(files[:3]):
            print(f"   📄 {file_path.name}")
            
        if len(files) > 3:
            print(f"   ... and {len(files) - 3} more files")
    else:
        print("📁 No uploads directory found")
        
def display_system_info():
    """Display system information and testing instructions"""
    print("\n" + "="*60)
    print("🎯 FinoktAI OCR System - Ready for Testing!")
    print("="*60)
    print(f"🌐 Web Interface: {BASE_URL}")
    print(f"📚 API Documentation: {BASE_URL}/docs")
    print("\n📋 Quick Test Steps:")
    print("1. Open http://localhost:8000 in your browser")
    print("2. Upload a PDF or image document") 
    print("3. Click on red bounding boxes to edit text")
    print("4. Check the 'Learning Stats' tab for analytics")
    print("5. Make the same correction 3 times to trigger lexicon learning")
    print("\n🔧 Advanced Testing:")
    print("- Check data/logs/corrections/ for correction logs")
    print("- Monitor data/training_data/ocr_samples/ for training data")
    print("- Use API endpoints for programmatic testing")
    print("\n📖 Full testing guide available in TESTING_GUIDE.md")

def main():
    """Run all tests"""
    print("🚀 Starting FinoktAI OCR System Tests...")
    print("="*50)
    
    # Test server health
    if not test_server_health():
        print("\n❌ Server is not running. Please start it first:")
        print("   uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        return
    
    # Test API endpoints
    api_results = test_api_endpoints()
    
    # Test file structure
    test_file_structure()
    
    # Check sample documents
    test_sample_documents()
    
    # Display summary and instructions
    display_system_info()
    
    # Show API results summary
    print("\n📊 API Test Results:")
    for endpoint, result in api_results.items():
        if result is not None:
            if endpoint == "/api/document_types":
                print(f"   📋 Document Types: {result.get('total_types', 0)} available")
            elif endpoint == "/api/lexicon":
                print(f"   🧠 Lexicon: {result.get('lexicon_size', 0)} auto-corrections")
            elif endpoint == "/api/training_data/stats":
                print(f"   🎯 Training Data: {result.get('total_samples', 0)} samples")
    
    print("\n🎉 System is ready for testing!")
    print("Open your browser and navigate to http://localhost:8000")

if __name__ == "__main__":
    main()

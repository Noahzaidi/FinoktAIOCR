#!/usr/bin/env python3
"""
Quick script to verify training samples are being created.
Run this after making a correction in the UI.
"""

from pathlib import Path
import json

def check_training_samples():
    """Check if training samples exist and display info."""
    training_dir = Path("data/training_data/ocr_samples")
    
    print("=" * 60)
    print("🔍 Training Samples Verification")
    print("=" * 60)
    
    if not training_dir.exists():
        print(f"❌ Training directory doesn't exist: {training_dir}")
        print("   Creating it now...")
        training_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {training_dir}")
        return
    
    # Count samples
    png_files = list(training_dir.glob("*.png"))
    json_files = list(training_dir.glob("*.json"))
    
    print(f"\n📁 Directory: {training_dir.absolute()}")
    print(f"\n📊 Sample Count:")
    print(f"   Images (PNG):  {len(png_files)}")
    print(f"   Metadata (JSON): {len(json_files)}")
    print(f"   Total Samples: {len(png_files)}")
    
    if len(png_files) == 0:
        print("\n⚠️  No training samples found yet!")
        print("\n💡 To create training samples:")
        print("   1. Go to http://localhost:8000/upload")
        print("   2. Upload a document")
        print("   3. Click on a red bounding box")
        print("   4. Edit the text and click 'Save Correction'")
        print("   5. Run this script again to verify")
        return
    
    # Show recent samples
    print(f"\n📝 Recent Training Samples (last 5):")
    print("-" * 60)
    
    sorted_json_files = sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]
    
    for i, json_file in enumerate(sorted_json_files, 1):
        try:
            with json_file.open('r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            print(f"\n{i}. {json_file.name}")
            print(f"   Original:  '{metadata.get('original_text', 'N/A')}'")
            print(f"   Corrected: '{metadata.get('corrected_text', 'N/A')}'")
            print(f"   Document:  {metadata.get('document_id', 'N/A')}")
            print(f"   Page:      {metadata.get('page', 'N/A')}")
            print(f"   Created:   {metadata.get('timestamp', 'N/A')}")
        except Exception as e:
            print(f"\n{i}. {json_file.name}")
            print(f"   ⚠️  Error reading metadata: {e}")
    
    # Status for retraining
    print("\n" + "=" * 60)
    if len(png_files) >= 10:
        print("✅ Ready for retraining! (10+ samples available)")
        print("   Go to Learning Stats tab → Advanced → Start Model Retraining")
    else:
        remaining = 10 - len(png_files)
        print(f"⏳ Need {remaining} more sample(s) for retraining")
        print(f"   Progress: {len(png_files)}/10")
    print("=" * 60)

if __name__ == "__main__":
    check_training_samples()


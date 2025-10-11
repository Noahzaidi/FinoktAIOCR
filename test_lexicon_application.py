#!/usr/bin/env python3
"""
Test if lexicon auto-corrections are being applied during OCR processing
"""

import json
from pathlib import Path
from ocr.lexicon_processor import get_lexicon_processor
from config_manager import get_config

def test_lexicon_application():
    """Test lexicon application with sample OCR data"""
    print("Testing lexicon auto-correction application...")
    
    # Load the actual lexicon
    config = get_config()
    processor = get_lexicon_processor(config)
    lexicon = processor._load_lexicon("document")
    
    print(f"Loaded lexicon: {len(lexicon)} patterns")
    for original, corrected in list(lexicon.items())[:3]:
        print(f"  '{original}' -> '{corrected}'")
    
    # Create sample OCR data with known errors
    sample_ocr_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            {
                                "words": [
                                    {
                                        "value": "ZAIDI<<NOUR<EDDINE<<<<<<<<<<",
                                        "confidence": 0.8,
                                        "geometry": [[0.1, 0.1], [0.5, 0.15]]
                                    },
                                    {
                                        "value": "LDAUTPA12345673<<<<<<",
                                        "confidence": 0.9,
                                        "geometry": [[0.1, 0.2], [0.5, 0.25]]
                                    },
                                    {
                                        "value": "NORMAL_WORD",
                                        "confidence": 0.95,
                                        "geometry": [[0.1, 0.3], [0.3, 0.35]]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    print(f"\nOriginal OCR data:")
    for page in sample_ocr_data["pages"]:
        for block in page["blocks"]:
            for line in block["lines"]:
                for word in line["words"]:
                    print(f"  '{word['value']}'")
    
    # Apply lexicon corrections
    corrected_data, applied_corrections = processor.apply_lexicon_corrections(sample_ocr_data, "document")
    
    print(f"\nAfter lexicon application:")
    print(f"Applied corrections: {applied_corrections}")
    
    for page in corrected_data["pages"]:
        for block in page["blocks"]:
            for line in block["lines"]:
                for word in line["words"]:
                    status = ""
                    if word.get("auto_corrected"):
                        status = " (AUTO-CORRECTED)"
                    print(f"  '{word['value']}'{status}")
                    if word.get("original_value"):
                        print(f"    Original: '{word['original_value']}'")

if __name__ == "__main__":
    test_lexicon_application()

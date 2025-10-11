
import re
import json
from pathlib import Path
from .patterns import PATTERNS

def normalize_text(text: str, document_type: str = "document") -> dict:
    """
    Enhanced text normalization with lexicon-based auto-corrections.
    Applies learned corrections before pattern extraction.
    """
    # Apply lexicon corrections first
    corrected_text, corrections_applied = apply_lexicon_corrections(text, document_type)
    
    extracted_data = {
        "invoice_number": None,
        "date": None,
        "amount": None,
        "currency": None,
        "country": None,
        "corrections_applied": corrections_applied,  # Track what corrections were applied
    }

    for key, pattern in PATTERNS.items():
        match = re.search(pattern, corrected_text, re.IGNORECASE | re.MULTILINE)
        if match and len(match.groups()) > 0:
            # Use the first captured group, which is more specific than the whole match.
            value = match.group(1)
            if value:
                extracted_data[key] = value.strip()

    # Enhanced normalization with document-type specific logic
    extracted_data = apply_document_type_normalization(extracted_data, document_type)

    # Basic normalization (existing logic)
    if extracted_data.get("amount"):
        # Remove anything that isn't a digit or a decimal point
        amount_str = re.sub(r'[^\d.]', '', str(extracted_data["amount"]))
        try:
            extracted_data["amount"] = float(amount_str)
        except (ValueError, TypeError):
            extracted_data["amount"] = None # Failed conversion

    if extracted_data.get("currency"):
        # Enhanced currency mapping
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
        symbol = re.search(r'[\$\€\£\¥₹]', str(extracted_data["currency"]))
        if symbol:
            extracted_data["currency"] = currency_map.get(symbol.group(0), "USD")

    # Enhanced country inference
    if extracted_data["currency"] == "USD":
        extracted_data["country"] = "US"
    elif extracted_data["currency"] == "EUR":
        extracted_data["country"] = "EU"
    elif extracted_data["currency"] == "GBP":
        extracted_data["country"] = "UK"
    elif extracted_data["currency"] == "JPY":
        extracted_data["country"] = "JP"
    elif extracted_data["currency"] == "INR":
        extracted_data["country"] = "IN"

    return extracted_data

def apply_lexicon_corrections(text: str, document_type: str = "document") -> tuple:
    """
    Apply learned lexicon corrections to text before processing.
    Returns tuple of (corrected_text, corrections_applied)
    """
    corrections_applied = []
    
    try:
        # Load global auto-corrections lexicon
        lexicon_path = Path("data/lexicons/auto_corrections.json")
        if not lexicon_path.exists():
            return text, corrections_applied
        
        with lexicon_path.open("r", encoding="utf-8") as f:
            lexicon = json.load(f)
        
        # Apply corrections
        corrected_text = text
        for original, corrected in lexicon.items():
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(original) + r'\b'
            if re.search(pattern, corrected_text, flags=re.IGNORECASE):
                corrected_text = re.sub(pattern, corrected, corrected_text, flags=re.IGNORECASE)
                corrections_applied.append(f"'{original}' → '{corrected}'")
        
        # Load document-type specific lexicon if available
        type_lexicon_path = Path(f"data/lexicons/{document_type}_corrections.json")
        if type_lexicon_path.exists():
            with type_lexicon_path.open("r", encoding="utf-8") as f:
                type_lexicon = json.load(f)
            
            for original, corrected in type_lexicon.items():
                pattern = r'\b' + re.escape(original) + r'\b'
                if re.search(pattern, corrected_text, flags=re.IGNORECASE):
                    corrected_text = re.sub(pattern, corrected, corrected_text, flags=re.IGNORECASE)
                    corrections_applied.append(f"'{original}' → '{corrected}' (type-specific)")
        
        return corrected_text, corrections_applied
        
    except Exception as e:
        # Log error but don't fail the whole process
        print(f"Warning: Lexicon correction failed: {e}")
        return text, corrections_applied

def get_applied_corrections(original_text: str, corrected_text: str) -> list:
    """
    Identify what corrections were applied (for transparency).
    """
    corrections = []
    
    # Simple diff-like approach to identify changes
    original_words = original_text.split()
    corrected_words = corrected_text.split()
    
    if len(original_words) == len(corrected_words):
        for i, (orig, corr) in enumerate(zip(original_words, corrected_words)):
            if orig != corr:
                corrections.append(f"'{orig}' -> '{corr}'")
    
    return corrections

def apply_document_type_normalization(extracted_data: dict, document_type: str) -> dict:
    """
    Apply document-type specific normalization rules.
    """
    if document_type == "invoice":
        # Invoice-specific normalization
        if extracted_data.get("invoice_number"):
            # Normalize invoice number format
            inv_num = str(extracted_data["invoice_number"]).upper()
            extracted_data["invoice_number"] = inv_num
        
        # Ensure amount is positive for invoices
        if extracted_data.get("amount") and extracted_data["amount"] < 0:
            extracted_data["amount"] = abs(extracted_data["amount"])
    
    elif document_type == "receipt":
        # Receipt-specific normalization
        if extracted_data.get("amount"):
            # Receipts typically have positive amounts
            extracted_data["amount"] = abs(extracted_data["amount"])
    
    elif document_type == "identity_document":
        # ID document specific normalization
        # Could add ID number formatting, name normalization, etc.
        pass
    
    return extracted_data


import re
from .patterns import PATTERNS

def normalize_text(text: str) -> dict:
    """
    Applies a series of regex patterns to extract structured fields from raw text.
    This is a stub implementation and should be expanded.
    """
    extracted_data = {
        "invoice_number": None,
        "date": None,
        "amount": None,
        "currency": None,
        "country": None, # Stubbed
    }

    for key, pattern in PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match and len(match.groups()) > 0:
            # Use the first captured group, which is more specific than the whole match.
            value = match.group(1)
            if value:
                extracted_data[key] = value.strip()

    # Basic normalization (stubs)
    if extracted_data.get("amount"):
        # Remove anything that isn't a digit or a decimal point
        amount_str = re.sub(r'[^\d.]', '', extracted_data["amount"])
        try:
            extracted_data["amount"] = float(amount_str)
        except (ValueError, TypeError):
            extracted_data["amount"] = None # Failed conversion

    if extracted_data.get("currency"):
        # Simple currency symbol to code mapping
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP"}
        symbol = re.search(r'[\$\€\£]', extracted_data["currency"])
        if symbol:
            extracted_data["currency"] = currency_map.get(symbol.group(0), "USD")

    # Country is stubbed, could be inferred from currency, address, etc.
    if extracted_data["currency"] == "USD":
        extracted_data["country"] = "US"
    elif extracted_data["currency"] == "EUR":
        extracted_data["country"] = "EU" # Ambiguous, just an example

    return extracted_data

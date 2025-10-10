# Regex patterns for extracting common invoice fields.
# These are examples and may need significant tuning for real-world documents.
# For your specific documents, you should:
#  1. Inspect the full OCR text output.
#  2. Identify the exact keywords and text format for each field.
#  3. Adjust these patterns accordingly. Online regex testers are very helpful for this.

PATTERNS = {
    # Look for keywords like 'Invoice Number', 'Invoice #', etc., followed by a value.
    # The value is captured in a group `([A-Z0-9-]{3,})` which requires at least 3 alphanumeric characters or hyphens.
    "invoice_number": r"(?:Invoice Number|Invoice #|Invoice No|Ref|Reference)\s*[: ]?\s*([A-Z0-9-]{3,})",

    # Look for dates in various formats (e.g., YYYY-MM-DD, DD/MM/YYYY, Month DD, YYYY)
    # The value is captured in a group `(...)`.
    "date": r"(?:Date|Invoice Date)\s*[: ]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/\.]\d{2}[/\.]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{1,2},?\s\d{4})",

    # Look for keywords like 'Total', 'Amount Due', etc., followed by a monetary value.
    # This pattern tries to capture a number with commas and a decimal part, optionally preceded by a currency symbol.
    "amount": r"(?:Total|Amount Due|Balance|Amount)\s*[: ]?\s*[\$\€\£]?\s?(\d{1,3}(?:,\d{3})*\.\d{2})",

    # A simpler pattern to just find a currency symbol near a total amount keyword.
    "currency": r"(?:Total|Amount Due|Balance).*?([\$\€\£])",
}
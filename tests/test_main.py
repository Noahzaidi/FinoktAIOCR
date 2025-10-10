import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import os
import sys
import json
from PIL import Image, ImageDraw, ImageFont

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app, UPLOAD_DIR, OUTPUT_DIR

client = TestClient(app)

@pytest.fixture(scope="module")
def test_image() -> Path:
    """Creates a simple dummy image with text for testing."""
    img_path = Path("test_invoice.png")
    img = Image.new('RGB', (400, 200), color = 'white')
    draw = ImageDraw.Draw(img)
    
    # Use a basic font
    try:
        font = ImageFont.truetype("arial.ttf", 25)
    except IOError:
        font = ImageFont.load_default()

    # Add some text to be OCR'd
    draw.text((10, 10), "Invoice Number: INV-123", fill='black', font=font)
    draw.text((10, 40), "Date: 2025-10-10", fill='black', font=font)
    draw.text((10, 70), "Total: $99.99", fill='black', font=font)
    
    img.save(img_path)
    yield img_path
    
    # Cleanup
    img_path.unlink()


def test_upload_and_process(test_image: Path):
    """Tests the entire upload, process, and export workflow."""
    # Clear output directory before test
    for f in OUTPUT_DIR.glob("*"):
        if f.is_file():
            f.unlink()

    with open(test_image, "rb") as f:
        response = client.post("/upload", files={"file": (test_image.name, f, "image/png")})
    
    assert response.status_code == 200
    assert "text/html" in response.headers['content-type']

    # The response body for /upload contains the doc_id in the HTML
    # We need to parse it out to continue the test.
    body = response.text
    start_str = '<strong id="doc-id">'
    end_str = '</strong>'
    start_index = body.find(start_str)
    assert start_index != -1, "Could not find doc-id in response"
    start_index += len(start_str)
    end_index = body.find(end_str, start_index)
    assert end_index != -1, "Could not find closing tag for doc-id"
    doc_id = body[start_index:end_index].strip()

    # 1. Check if OCR output files were created
    ocr_json_path = OUTPUT_DIR / f"{doc_id}.json"
    page_image_path = OUTPUT_DIR / f"{doc_id}_page_0.png"
    assert ocr_json_path.exists()
    assert page_image_path.exists()

    # 2. Check content of OCR json
    with ocr_json_path.open("r") as f:
        ocr_data = json.load(f)
    assert "pages" in ocr_data
    assert len(ocr_data["pages"]) == 1

    # 3. Test the export endpoint
    export_response = client.get(f"/export/{doc_id}")
    assert export_response.status_code == 200
    structured_data = export_response.json()

    # 4. Verify structured data (based on our dummy image)
    assert structured_data["document_id"] == doc_id
    assert structured_data["invoice_number"] == "INV-123"
    assert structured_data["date"] == "2025-10-10"
    assert structured_data["amount"] == 99.99
    assert structured_data["currency"] == "USD"
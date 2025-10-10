import os
from pathlib import Path
import json
import logging

from PIL import Image
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

# Initialize the OCR predictor once
# This will download the model weights on the first run
predictor = ocr_predictor(pretrained=True, detect_orientation=True)

async def process_document(file_path: Path, doc_id: str, output_dir: Path) -> Path:
    """
    Processes a single document (PDF or image) using DocTR.
    - Uses from_pdf for PDF files.
    - Uses from_images for image files.
    - Runs OCR.
    - Saves the OCR JSON output.
    - Saves the first page as a PNG for the review UI.
    """
    logger = logging.getLogger(__name__)

    try:
        if file_path.suffix.lower() in (".pdf",):
            # Let DocTR handle the PDF conversion directly
            logger.info(f"Processing PDF file with from_pdf: {file_path}")
            doc = DocumentFile.from_pdf(file_path)
        else:
            # Handle images
            logger.info(f"Processing image file with from_images: {file_path}")
            doc = DocumentFile.from_images([file_path])
    except Exception as e:
        logger.error(f"DocTR failed to read the document: {e}")
        raise

    # The 'doc' object is a list of pages (numpy arrays)
    # Save all pages for the UI
    if len(doc) > 0:
        for page_idx, page_array in enumerate(doc):
            try:
                page_img = Image.fromarray(page_array)
                max_dim = 1024
                if max(page_img.width, page_img.height) > max_dim:
                    page_img.thumbnail((max_dim, max_dim))
                page_img.save(output_dir / f"{doc_id}_page_{page_idx}.png")
                logger.info(f"Saved page {page_idx + 1} image: {doc_id}_page_{page_idx}.png")
            except Exception as e:
                logger.error(f"Failed to save page {page_idx + 1} image: {e}")
                # Continue with other pages

    # Run OCR
    result = predictor(doc)
    
    # Export the result as a dictionary
    ocr_dict = result.export()

    # Save the full OCR JSON output
    output_path = output_dir / f"{doc_id}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(ocr_dict, f, ensure_ascii=False, indent=4)

    return output_path
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

async def process_document(file_path: Path, doc_id: str, output_dir: Path) -> (dict, list):
    """
    Processes a single document (PDF or image) using DocTR.
    - Runs OCR.
    - Returns the OCR data as a dictionary.
    - Saves page images and returns their paths.
    """
    logger = logging.getLogger(__name__)
    image_paths = []

    try:
        if file_path.suffix.lower() in (".pdf",):
            doc = DocumentFile.from_pdf(file_path)
        else:
            doc = DocumentFile.from_images([file_path])
    except Exception as e:
        logger.error(f"DocTR failed to read the document: {e}")
        raise

    if len(doc) > 0:
        for page_idx, page_array in enumerate(doc):
            try:
                page_img = Image.fromarray(page_array)
                max_dim = 1024
                if max(page_img.width, page_img.height) > max_dim:
                    page_img.thumbnail((max_dim, max_dim))
                
                image_path = output_dir / f"{doc_id}_page_{page_idx}.png"
                page_img.save(image_path)
                # Store only the filename, not the full path
                image_paths.append(image_path.name)
                logger.info(f"Saved page {page_idx + 1} image: {image_path.name}")
            except Exception as e:
                logger.error(f"Failed to save page {page_idx + 1} image: {e}")

    result = predictor(doc)
    ocr_dict = result.export()

    return ocr_dict, image_paths
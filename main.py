
import os
import uuid
import json
from pathlib import Path
import shutil
from typing import Dict

import logging
import traceback

from fastapi import FastAPI, File, UploadFile, Request, Form

# Add basic logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from ocr.doctr_ocr import process_document
from postprocessing.normalize import normalize_text
from postprocessing.anchors import get_anchor_extractor
from layout.layout_inference import process_layout
from quality.scoring import get_quality_scorer, get_document_router
from corrections.integration import get_correction_integrator, get_correction_learner

# Configuration
UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FinoktAI OCR Learning & Structuring System")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_upload_form(request: Request):
    """Serves the main page with the file upload form."""
    return templates.TemplateResponse(request, "index.html")

@app.post("/upload", response_class=HTMLResponse)
async def upload_and_process_document(request: Request, file: UploadFile = File(...)):
    """Handles file upload, saves the file, and triggers OCR processing."""
    doc_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix
    upload_path = UPLOAD_DIR / f"{doc_id}{file_extension}"
    
    # Save the uploaded file
    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process the document with enhanced pipeline
    try:
        logger.info(f"Processing document: {upload_path}")
        
        # Step 1: OCR Processing
        ocr_output_path = await process_document(upload_path, doc_id, OUTPUT_DIR)
        logger.info(f"OCR processing completed for document: {doc_id}")
        
        # Load OCR data for further processing
        with ocr_output_path.open("r", encoding="utf-8") as f:
            ocr_data = json.load(f)
        
        # Step 2: Layout Inference (LayoutLMv3)
        image_path = OUTPUT_DIR / f"{doc_id}_page_0.png"
        layout_data = await process_layout(image_path, ocr_data, doc_id)
        
        # Save layout analysis results
        layout_output_path = OUTPUT_DIR / f"{doc_id}_layout.json"
        with layout_output_path.open("w", encoding="utf-8") as f:
            json.dump(layout_data, f, ensure_ascii=False, indent=2)
        
        # Step 3: Enhanced Field Extraction (Anchor-based + Regex)
        anchor_extractor = get_anchor_extractor()
        anchored_fields = anchor_extractor.extract_anchored_fields(ocr_data)
        
        # Combine with traditional regex extraction
        full_text = " ".join(
            word['value'] 
            for page in ocr_data.get('pages', [])
            for block in page.get('blocks', [])
            for line in block.get('lines', [])
            for word in line.get('words', [])
        )
        regex_fields = normalize_text(full_text)
        
        # Merge extraction results (anchored fields take precedence)
        extracted_fields = {**regex_fields, **anchored_fields}
        
        # Save enhanced extraction results
        extraction_output_path = OUTPUT_DIR / f"{doc_id}_extracted.json"
        with extraction_output_path.open("w", encoding="utf-8") as f:
            json.dump(extracted_fields, f, ensure_ascii=False, indent=2)
        
        # Save raw OCR data in structured format
        raw_ocr_data = _extract_raw_ocr_structure(ocr_data, doc_id)
        raw_ocr_output_path = OUTPUT_DIR / f"{doc_id}_raw.json"
        with raw_ocr_output_path.open("w", encoding="utf-8") as f:
            json.dump(raw_ocr_data, f, ensure_ascii=False, indent=2)
        
        # Step 4: Quality Assessment
        quality_scorer = get_quality_scorer()
        quality_metrics = quality_scorer.compute_quality_score(
            ocr_data, layout_data, extracted_fields
        )
        
        # Step 5: Document Routing
        document_router = get_document_router()
        routing_decision = document_router.route_document(doc_id, quality_metrics)
        
        # Save quality assessment and routing
        quality_output_path = OUTPUT_DIR / f"{doc_id}_quality.json"
        with quality_output_path.open("w", encoding="utf-8") as f:
            json.dump({
                "quality_metrics": {
                    "ocr_confidence": quality_metrics.ocr_confidence,
                    "layout_confidence": quality_metrics.layout_confidence,
                    "field_extraction_confidence": quality_metrics.field_extraction_confidence,
                    "overall_quality": quality_metrics.overall_quality,
                    "quality_level": quality_metrics.quality_level.value,
                    "recommendations": quality_metrics.recommendations
                },
                "routing_decision": routing_decision
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Document processing completed: {doc_id} "
                   f"(Quality: {quality_metrics.overall_quality:.3f}, "
                   f"Level: {quality_metrics.quality_level.value})")
        
        # Return to review page with processing results
        return templates.TemplateResponse(request, "canvas.html", {
            "doc_id": doc_id,
            "message": f"Document processed successfully! Quality: {quality_metrics.quality_level.value.title()}",
            "quality_level": quality_metrics.quality_level.value,
            "overall_quality": f"{quality_metrics.overall_quality:.1%}",
            "recommendations": quality_metrics.recommendations
        })
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Failed to process document: {doc_id}")
        logger.error(f"Error: {e}")
        logger.error(f"Traceback:\n{error_details}")
        return JSONResponse(status_code=500, content={"error": f"Failed to process document: {str(e)}"})

@app.get("/review/{doc_id}", response_class=HTMLResponse)
async def get_review_ui(request: Request, doc_id: str):
    """Serves the human-in-the-loop review UI."""
    return templates.TemplateResponse(request, "canvas.html", {"doc_id": doc_id})

@app.get("/data/document/{doc_id}")
async def get_document_data(doc_id: str):
    """
    Provides the necessary data for the review UI:
    1. The path to the first page image of the document.
    2. The raw OCR JSON data.
    """
    # Construct the paths to the generated files
    page_image_path = OUTPUT_DIR / f"{doc_id}_page_0.png"
    ocr_json_path = OUTPUT_DIR / f"{doc_id}.json"

    # Check if the files exist
    if not page_image_path.exists() or not ocr_json_path.exists():
        return JSONResponse(status_code=404, content={"error": "Document data not found."})

    with ocr_json_path.open("r", encoding="utf-8") as f:
        ocr_data = json.load(f)

    return JSONResponse(content={
        "imageUrl": f"/data/outputs/{doc_id}_page_0.png",
        "ocrData": ocr_data
    })
    
@app.get("/data/outputs/{filename}")
async def get_output_file(filename: str):
    """Serves generated files like images from the output directory."""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found."})
    return FileResponse(str(file_path))

@app.get("/api/quality/{doc_id}")
async def get_quality_metrics(doc_id: str):
    """Get quality metrics and routing information for a document."""
    quality_path = OUTPUT_DIR / f"{doc_id}_quality.json"
    if not quality_path.exists():
        return JSONResponse(status_code=404, content={"error": "Quality metrics not found."})
    
    with quality_path.open("r", encoding="utf-8") as f:
        quality_data = json.load(f)
    
    return JSONResponse(content=quality_data)

@app.get("/api/corrections/stats/{doc_id}")
async def get_correction_statistics(doc_id: str):
    """Get correction statistics for a document."""
    corrections_log_path = OUTPUT_DIR / f"{doc_id}_corrections.log"
    
    correction_integrator = get_correction_integrator()
    stats = correction_integrator.get_correction_statistics(corrections_log_path, doc_id)
    
    return JSONResponse(content=stats)

@app.get("/raw_ocr/{doc_id}")
async def get_raw_ocr_data(doc_id: str):
    """
    Get structured raw OCR data with word-level information.
    Returns JSON with text, bounding boxes, and confidence scores.
    """
    raw_ocr_path = OUTPUT_DIR / f"{doc_id}_raw.json"
    if not raw_ocr_path.exists():
        return JSONResponse(status_code=404, content={"error": "Raw OCR data not found."})
    
    with raw_ocr_path.open("r", encoding="utf-8") as f:
        raw_ocr_data = json.load(f)
    
    return JSONResponse(content=raw_ocr_data)


@app.post("/save_correction")
async def save_correction(
    doc_id: str = Form(...),
    page: int = Form(...),
    word_id: str = Form(...),
    corrected_text: str = Form(...),
    corrected_bbox: str = Form(...), # JSON string of a list
    user_id: str = Form("analyst1")
):
    """Saves a user's correction to a log file."""
    log_path = OUTPUT_DIR / f"{doc_id}_corrections.log"
    
    try:
        bbox = json.loads(corrected_bbox)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid bbox format."})

    log_entry = {
        "document_id": doc_id,
        "page": page,
        "word_id": word_id,
        "corrected_text": corrected_text,
        "corrected_bbox": bbox,
        "user_id": user_id,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat()
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    return JSONResponse(content={"status": "success", "message": "Correction saved."})

@app.get("/export/{doc_id}")
async def export_structured_data(doc_id: str, format: str = "json"):
    """
    Export structured data with applied corrections and enhanced processing.
    Supports multiple formats: json, csv, xml
    """
    ocr_json_path = OUTPUT_DIR / f"{doc_id}.json"
    if not ocr_json_path.exists():
        return JSONResponse(status_code=404, content={"error": "OCR data not found."})

    # Load original OCR data
    with ocr_json_path.open("r", encoding="utf-8") as f:
        ocr_data = json.load(f)
    
    # Apply corrections from log
    corrections_log_path = OUTPUT_DIR / f"{doc_id}_corrections.log"
    correction_integrator = get_correction_integrator()
    
    corrected_ocr_data, corrected_extracted_fields = correction_integrator.apply_corrections_to_export(
        doc_id, ocr_data, {}, corrections_log_path
    )
    
    # Load enhanced extraction results if available
    extraction_path = OUTPUT_DIR / f"{doc_id}_extracted.json"
    if extraction_path.exists():
        with extraction_path.open("r", encoding="utf-8") as f:
            enhanced_fields = json.load(f)
        # Merge with corrected fields (corrections take precedence)
        final_fields = {**enhanced_fields, **corrected_extracted_fields}
    else:
        # Fallback to basic extraction
        full_text = " ".join(
            word['value'] 
            for page in corrected_ocr_data.get('pages', [])
            for block in page.get('blocks', [])
            for line in block.get('lines', [])
            for word in line.get('words', [])
        )
        final_fields = normalize_text(full_text)
    
    # Add document metadata
    final_fields["document_id"] = doc_id
    final_fields["export_timestamp"] = __import__("datetime").datetime.utcnow().isoformat()
    
    # Load quality metrics if available
    quality_path = OUTPUT_DIR / f"{doc_id}_quality.json"
    if quality_path.exists():
        with quality_path.open("r", encoding="utf-8") as f:
            quality_data = json.load(f)
        final_fields["quality_assessment"] = quality_data["quality_metrics"]
        final_fields["routing_info"] = quality_data["routing_decision"]
    
    # Update correction lexicon for learning
    correction_learner = get_correction_learner()
    correction_learner.update_correction_lexicon(corrections_log_path)
    
    # Return in requested format
    if format.lower() == "csv":
        return _export_as_csv(final_fields)
    elif format.lower() == "xml":
        return _export_as_xml(final_fields)
    else:  # Default to JSON
        return JSONResponse(content=final_fields)

def _extract_raw_ocr_structure(ocr_data: Dict, doc_id: str) -> Dict:
    """
    Extract structured raw OCR data in the requested format.
    
    Args:
        ocr_data: DocTR OCR output
        doc_id: Document identifier
        
    Returns:
        Structured JSON with word-level data
    """
    structured_data = {
        "document_id": doc_id,
        "extraction_timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "pages": []
    }
    
    for page_idx, page in enumerate(ocr_data.get("pages", [])):
        page_data = {
            "page_num": page_idx + 1,
            "words": []
        }
        
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    # Extract word data
                    text = word.get("value", "").strip()
                    if not text:  # Skip empty words
                        continue
                    
                    # Get bounding box (DocTR uses relative coordinates [0,1])
                    geometry = word.get("geometry", [[0, 0, 0, 0]])[0]
                    bbox = [float(coord) for coord in geometry]  # [x1, y1, x2, y2]
                    
                    # Get confidence score
                    confidence = word.get("confidence", 0.0)
                    
                    word_data = {
                        "text": text,
                        "bbox": bbox,
                        "confidence": round(float(confidence), 4) if confidence else 0.0
                    }
                    
                    page_data["words"].append(word_data)
        
        # Add page statistics
        page_data["word_count"] = len(page_data["words"])
        if page_data["words"]:
            avg_confidence = sum(w["confidence"] for w in page_data["words"]) / len(page_data["words"])
            page_data["average_confidence"] = round(avg_confidence, 4)
        else:
            page_data["average_confidence"] = 0.0
            
        structured_data["pages"].append(page_data)
    
    # Add document-level statistics
    total_words = sum(page["word_count"] for page in structured_data["pages"])
    if total_words > 0:
        total_confidence = sum(
            page["average_confidence"] * page["word_count"] 
            for page in structured_data["pages"]
        )
        structured_data["total_words"] = total_words
        structured_data["overall_confidence"] = round(total_confidence / total_words, 4)
    else:
        structured_data["total_words"] = 0
        structured_data["overall_confidence"] = 0.0
    
    return structured_data

def _export_as_csv(data: Dict) -> FileResponse:
    """Export data as CSV file."""
    import csv
    import tempfile
    
    # Create temporary CSV file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
    
    try:
        writer = csv.writer(temp_file)
        
        # Write headers and values
        writer.writerow(['Field', 'Value'])
        for key, value in data.items():
            if not isinstance(value, (dict, list)):  # Skip complex objects
                writer.writerow([key, str(value)])
        
        temp_file.close()
        
        return FileResponse(
            temp_file.name,
            media_type='text/csv',
            filename=f"{data.get('document_id', 'document')}.csv"
        )
    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        temp_file.close()
        return JSONResponse(status_code=500, content={"error": "CSV export failed"})

def _export_as_xml(data: Dict) -> FileResponse:
    """Export data as XML file."""
    import tempfile
    import xml.etree.ElementTree as ET
    
    # Create temporary XML file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8')
    
    try:
        # Create XML structure
        root = ET.Element('document')
        root.set('id', str(data.get('document_id', 'unknown')))
        
        for key, value in data.items():
            if not isinstance(value, (dict, list)):  # Skip complex objects
                elem = ET.SubElement(root, key.replace(' ', '_'))
                elem.text = str(value)
        
        # Write XML to file
        tree = ET.ElementTree(root)
        tree.write(temp_file.name, encoding='utf-8', xml_declaration=True)
        temp_file.close()
        
        return FileResponse(
            temp_file.name,
            media_type='application/xml',
            filename=f"{data.get('document_id', 'document')}.xml"
        )
    except Exception as e:
        logger.error(f"XML export failed: {e}")
        temp_file.close()
        return JSONResponse(status_code=500, content={"error": "XML export failed"})

if __name__ == "__main__":
    import uvicorn
    # To run: uvicorn main:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8000)

import os
import uuid
import json
from pathlib import Path
import shutil
from typing import Dict, List
import logging
import traceback
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Request, Form, Depends
from sqlalchemy.orm import Session

# Add basic logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Database imports
from database.connector import SessionLocal, engine, get_db
from database import models

from ocr.doctr_ocr import process_document
from postprocessing.normalize import normalize_text
from postprocessing.anchors import get_anchor_extractor
from layout.layout_inference import process_layout
from quality.scoring import get_quality_scorer, get_document_router
from corrections.integration import get_correction_integrator, get_correction_learner
from classification.document_classifier import get_document_classifier
from config_manager import get_config
from ocr.lexicon_processor import get_lexicon_processor

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Configuration - use absolute paths
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
OUTPUT_DIR = BASE_DIR / "data" / "outputs"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FinoktAI OCR Learning & Structuring System")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/", response_class=HTMLResponse)
async def get_upload_form(request: Request):
    """Serves the main page with the file upload form."""
    return templates.TemplateResponse(request, "index.html")

@app.get("/test-corrections", response_class=HTMLResponse)
async def test_corrections_page(request: Request):
    """Test page to verify corrections are being applied."""
    return templates.TemplateResponse(request, "test_corrections.html")

@app.post("/upload", response_class=HTMLResponse)
async def upload_and_process_document(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Handles file upload, saves the file, and triggers OCR processing."""
    doc_id = uuid.uuid4()
    file_extension = Path(file.filename).suffix
    storage_path = UPLOAD_DIR / f"{doc_id}{file_extension}"

    # Save the uploaded file
    with storage_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create a new document record in the database
    db_document = models.Document(
        id=doc_id, 
        filename=file.filename, 
        content_type=file.content_type,
        storage_path=str(storage_path),
        status='processing'
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    try:
        logger.info(f"Processing document: {storage_path}")
        
        ocr_data, image_paths = await process_document(storage_path, str(doc_id), OUTPUT_DIR)
        logger.info(f"OCR processing completed for document: {doc_id}")

        for page_idx, page_data in enumerate(ocr_data.get("pages", [])):
            db_page = models.Page(
                document_id=db_document.id,
                page_number=page_idx,
                image_path=image_paths[page_idx],
                dimensions=page_data.get('dimensions')
            )
            db.add(db_page)
            db.commit()
            db.refresh(db_page)

            words_to_insert = []
            for block in page_data.get("blocks", []):
                for line in block.get("lines", []):
                    for word_info in line.get("words", []):
                        words_to_insert.append(models.Word(
                            page_id=db_page.id,
                            text=word_info.get('value'),
                            confidence=word_info.get('confidence'),
                            geometry=word_info.get('geometry')
                        ))
            db.bulk_save_objects(words_to_insert)
            db.commit()

        db_document.processed_at = datetime.utcnow()
        db_document.status = 'completed'
        db.commit()

        return templates.TemplateResponse(request, "canvas.html", {
            "doc_id": str(doc_id),
            "message": f"Document processed successfully!",
        })
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Failed to process document: {doc_id}")
        logger.error(f"Error: {e}")
        logger.error(f"Traceback:\n{error_details}")
        db_document.status = 'failed'
        db_document.processing_error = error_details
        db.commit()
        return JSONResponse(status_code=500, content={"error": f"Failed to process document: {str(e)}"})

@app.get("/review/{doc_id}", response_class=HTMLResponse)
async def get_review_ui(request: Request, doc_id: str):
    """Serves the human-in-the-loop review UI."""
    return templates.TemplateResponse(request, "canvas.html", {
        "doc_id": doc_id,
        "timestamp": int(datetime.now().timestamp())
    })

def apply_corrections_to_ocr_data(ocr_data: Dict, corrections: List) -> Dict:
    """
    GLOBAL LEARNING STRATEGY: Apply corrections to OCR data with intelligent fuzzy matching.
    
    Corrections apply globally across all documents using multiple strategies:
    - Exact match
    - Fuzzy match (strips special chars like *, <, etc.)
    - Prefix match (ZAIDI matches ZAIDI*, ZAIDI<NOUR, etc.)
    - Case-insensitive match
    
    Latest corrections always win (timestamp DESC).
    """
    if not corrections:
        return ocr_data
    
    # Sort by timestamp DESC (latest first)
    sorted_corrections = sorted(
        corrections, 
        key=lambda c: c.timestamp if c.timestamp else datetime.min,
        reverse=True
    )
    
    # Build correction mappings with TIMESTAMPS to ensure latest wins
    exact_match_map = {}  # key -> (corrected_text, timestamp)
    fuzzy_match_map = {}  # key -> (corrected_text, timestamp)
    prefix_match_list = []  # (original, corrected, timestamp)
    
    for correction in sorted_corrections:  # Already sorted by timestamp DESC (newest first)
        original = correction.original_text
        corrected = correction.corrected_text
        timestamp = correction.timestamp if correction.timestamp else datetime.min
        
        # Exact match - only keep if this is newer
        if original not in exact_match_map or timestamp > exact_match_map[original][1]:
            exact_match_map[original] = (corrected, timestamp)
        
        # Fuzzy match - only keep if this is newer
        original_clean = original.rstrip('<*. ')
        if original_clean:
            if original_clean not in fuzzy_match_map or timestamp > fuzzy_match_map[original_clean][1]:
                fuzzy_match_map[original_clean] = (corrected, timestamp)
        
        # Store ALL for prefix matching (will check timestamp when applying)
        prefix_match_list.append((original, corrected, timestamp))
    
    corrections_applied = 0
    
    # Apply corrections - CHECK ALL STRATEGIES and pick the NEWEST one
    for page in ocr_data.get("pages", []):
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    original_value = word.get("value", "")
                    if not original_value:
                        continue
                    
                    # CRITICAL: Find ALL matches and pick NEWEST by timestamp
                    # Timestamp is MORE important than match type for learning strategy
                    
                    candidates = []  # (corrected_value, timestamp, method, priority)
                    value_clean = original_value.rstrip('<*. ')
                    
                    # Strategy 1: Exact match (priority 1)
                    if original_value in exact_match_map:
                        corr_text, corr_time = exact_match_map[original_value]
                        candidates.append((corr_text, corr_time, "exact", 1))
                    
                    # Strategy 2: Fuzzy match (priority 2)
                    if value_clean in fuzzy_match_map:
                        corr_text, corr_time = fuzzy_match_map[value_clean]
                        candidates.append((corr_text, corr_time, "fuzzy", 2))
                    
                    # Strategy 3: Prefix match (priority 3)
                    for orig, corr, corr_time in prefix_match_list:
                        orig_clean = orig.rstrip('<*. ')
                        if orig_clean and value_clean.startswith(orig_clean):
                            # Don't apply prefix if we have exact match for full MRZ code
                            # Only apply prefix for simple cases
                            if len(original_value) - len(orig_clean) < 5:  # Short suffix ok
                                suffix = original_value[len(orig_clean):]
                                result = corr + suffix
                                candidates.append((result, corr_time, "prefix", 3))
                    
                    # Strategy 4: Case-insensitive (priority 4)
                    for exact_original, (exact_corrected, corr_time) in exact_match_map.items():
                        if exact_original.lower() == original_value.lower() and exact_original != original_value:
                            candidates.append((exact_corrected, corr_time, "case_insensitive", 4))
                    
                    # Pick correction: NEWEST timestamp wins
                    # If timestamps are equal, lower priority number wins
                    if candidates:
                        candidates.sort(key=lambda x: (x[1], -x[3]), reverse=True)
                        best_correction, best_time, best_method, _ = candidates[0]
                        
                        word["value"] = best_correction
                        word["corrected"] = True
                        word["original_value"] = original_value
                        word["correction_method"] = best_method
                        corrections_applied += 1
    
    if corrections_applied > 0:
        logger.info(f"Applied {corrections_applied} corrections to OCR data")
    
    return ocr_data

@app.get("/data/document/{doc_id}")
async def get_document_data(doc_id: str, db: Session = Depends(get_db)):
    """Provides the necessary data for the review UI from the database."""
    document = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not document or not document.pages:
        return JSONResponse(status_code=404, content={"error": "Document data not found."})

    # Reconstruct the ocr_data structure from database models
    # Group words into lines based on Y-coordinate proximity
    def group_words_into_lines(words, y_tolerance=0.015):
        """Group words into lines based on their Y-coordinates.
        
        Args:
            words: List of Word objects from database
            y_tolerance: Maximum Y-coordinate difference for same line (normalized 0-1)
        """
        if not words:
            return []
        
        # Sort words by Y coordinate (top to bottom), then X (left to right)
        # Geometry can be either [x, y] or [[x1, y1], [x2, y2]]
        def get_coords(w):
            if not w.geometry or len(w.geometry) < 2:
                return (0, 0)
            # Check if it's a bounding box [[x1,y1],[x2,y2]] or single point [x,y]
            if isinstance(w.geometry[0], list):
                return (w.geometry[0][1], w.geometry[0][0])  # Y, X
            else:
                return (w.geometry[1], w.geometry[0])  # Y is at index 1, X at index 0
        
        sorted_words = sorted(words, key=get_coords)
        
        lines = []
        current_line = []
        current_y = None
        
        for word in sorted_words:
            if not word.geometry or len(word.geometry) < 2:
                continue
            
            # Get Y coordinate
            word_y = word.geometry[1] if not isinstance(word.geometry[0], list) else word.geometry[0][1]
            
            # Start new line if Y coordinate differs significantly
            if current_y is None or abs(word_y - current_y) > y_tolerance:
                if current_line:
                    lines.append(current_line)
                current_line = []
                current_y = word_y
            
            current_line.append({
                "value": word.text,
                "confidence": word.confidence,
                "geometry": word.geometry
            })
        
        # Add the last line
        if current_line:
            lines.append(current_line)
        
        return lines
    
    ocr_data = {
        "doc_id": str(document.id),
        "pages": []
    }
    
    for page in document.pages:
        lines = group_words_into_lines(page.words)
        page_data = {
            "page_idx": page.page_number,
            "dimensions": page.dimensions,
            "blocks": [
                {
                    "lines": [
                        {"words": line} for line in lines
                    ]
                }
            ] if lines else []
        }
        ocr_data["pages"].append(page_data)

    # Load and apply corrections (sorted by timestamp DESC - latest first)
    # Apply ALL corrections from database, not just document-specific ones
    try:
        # Get document-specific corrections
        doc_corrections = db.query(models.Correction).filter(
            models.Correction.document_id == doc_id
        ).order_by(models.Correction.timestamp.desc()).all()
        
        # Get global corrections (from other documents with same text patterns)
        global_corrections = db.query(models.Correction).filter(
            models.Correction.document_id != doc_id
        ).order_by(models.Correction.timestamp.desc()).all()
        
        # Combine: document-specific first, then global
        all_corrections = doc_corrections + global_corrections
        
        if all_corrections:
            logger.info(f"Applying {len(doc_corrections)} document + {len(global_corrections)} global corrections to {doc_id}")
            ocr_data = apply_corrections_to_ocr_data(ocr_data, all_corrections)
    except Exception as e:
        logger.error(f"Error applying corrections: {e}")
        import traceback
        traceback.print_exc()
        # Continue without corrections if there's an error
    
    # Handle both old absolute paths and new relative paths
    image_paths = []
    for page in document.pages:
        # Extract just the filename from path (handles both absolute and relative paths)
        image_filename = Path(page.image_path).name if page.image_path else None
        if image_filename:
            image_paths.append(f"/data/outputs/{image_filename}")
    
    response_content = {
        "imageUrl": image_paths[0] if image_paths else None,
        "imagePaths": image_paths,  # All page images
        "ocrData": ocr_data
    }
    
    # Add cache-busting headers to ensure fresh corrections
    return JSONResponse(
        content=response_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
    
@app.get("/api/quality/{doc_id}")
async def get_quality_metrics(doc_id: str, db: Session = Depends(get_db)):
    """Get quality metrics for a document from the database."""
    document = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not document:
        return JSONResponse(status_code=404, content={"error": "Quality metrics not found."})
    
    return JSONResponse(content={"quality_score": document.quality_score})

@app.get("/api/lexicon")
async def get_lexicon_data(db: Session = Depends(get_db)):
    """Get current lexicon data for review from the database."""
    try:
        lexicon_entries = db.query(models.Lexicon).all()
        lexicon_data = {entry.misspelled: entry.corrected for entry in lexicon_entries}
        frequency_data = {entry.misspelled: entry.frequency for entry in lexicon_entries}
        
        return JSONResponse(content={
            "lexicon": lexicon_data,
            "frequency": frequency_data,
            "lexicon_size": len(lexicon_data),
            "total_patterns": len(frequency_data)
        })
        
    except Exception as e:
        logger.error(f"Failed to get lexicon data: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve lexicon data"})

@app.get("/api/training_data/stats")
async def get_training_data_stats(db: Session = Depends(get_db)):
    """Get statistics about training data preparation from the database."""
    try:
        total_samples = db.query(models.TrainingSample).count()
        recent_samples = db.query(models.TrainingSample).order_by(models.TrainingSample.created_at.desc()).limit(10).all()
        
        return JSONResponse(content={
            "total_samples": total_samples,
            "recent_samples": [
                {
                    "label": sample.label,
                    "timestamp": sample.created_at.isoformat(),
                    "image_filename": sample.image_path
                } for sample in recent_samples
            ]
        })
        
    except Exception as e:
        logger.error(f"Failed to get training data stats: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve training data stats"})

@app.post("/save_correction")
async def save_correction(
    doc_id: str = Form(...),
    word_id: str = Form(...), # Custom ID from frontend, e.g., p0_w123
    original_text: str = Form(...),
    corrected_text: str = Form(...),
    corrected_bbox: str = Form(None),  # Optional bounding box as JSON string
    db: Session = Depends(get_db)
):
    """Saves a correction to the database."""
    logger.info(f"=== SAVE CORRECTION REQUEST ===")
    logger.info(f"Doc ID: {doc_id}")
    logger.info(f"Word ID: {word_id}")
    logger.info(f"Original: '{original_text}'")
    logger.info(f"Corrected: '{corrected_text}'")
    
    if original_text == corrected_text:
        logger.warning("No change detected - original equals corrected")
        return JSONResponse(content={"status": "success", "message": "No change detected"})

    try:
        # Convert doc_id to UUID
        from uuid import UUID
        try:
            doc_uuid = UUID(doc_id)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid document ID"})
        
        # Extract page number from word_id (e.g., "p0_w123" -> page 0)
        page_number = None
        if word_id and word_id.startswith('p'):
            try:
                page_number = int(word_id.split('_')[0][1:])
            except:
                pass
        
        # Parse bounding box if provided
        bbox_data = None
        if corrected_bbox:
            try:
                bbox_data = json.loads(corrected_bbox)
            except:
                pass
        
        # Create context data with extra information
        context_data = {
            'word_id': word_id,
            'page': page_number,
            'user_id': 'ui_user',
            'saved_at': datetime.now().isoformat()
        }
        if bbox_data:
            context_data['corrected_bbox'] = bbox_data
        
        # Save to Correction table
        db_correction = models.Correction(
            document_id=doc_uuid,
            word_id=None,  # word_id is string, not UUID
            original_text=original_text,
            corrected_text=corrected_text,
            context=json.dumps(context_data),
            timestamp=datetime.now()
        )
        db.add(db_correction)
        db.commit()
        db.refresh(db_correction)
        
        logger.info(f"✓ CORRECTION SAVED TO DATABASE")
        logger.info(f"  Correction ID: {db_correction.id}")
        logger.info(f"  Original: '{original_text}'")
        logger.info(f"  Corrected: '{corrected_text}'")
        logger.info(f"  Document: {doc_id}")
        logger.info(f"  Timestamp: {db_correction.timestamp}")
        
        # Verify it was saved
        verify = db.query(models.Correction).filter(models.Correction.id == db_correction.id).first()
        if verify:
            logger.info(f"✓ VERIFIED: Correction exists in database")
        else:
            logger.error(f"✗ ERROR: Correction not found after commit!")

        return JSONResponse(content={
            "status": "success", 
            "message": "Correction saved successfully",
            "correction_id": str(db_correction.id),
            "saved": True
        })

    except Exception as e:
        db.rollback()
        logger.error(f"SAVE_CORRECTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Save failed: {str(e)}"})

@app.post("/update_ocr_data/{doc_id}")
async def update_ocr_data(doc_id: str, request: Request, db: Session = Depends(get_db)):
    """Update OCR data after correction is made - return fresh corrected data."""
    try:
        logger.info(f"Fetching updated OCR data with corrections for {doc_id}")
        
        # Get document
        document = db.query(models.Document).filter(models.Document.id == doc_id).first()
        if not document:
            return JSONResponse(status_code=404, content={"error": "Document not found"})
        
        # Rebuild OCR data with corrections applied
        def group_words_into_lines(words, y_tolerance=0.015):
            if not words:
                return []
            def get_coords(w):
                if not w.geometry or len(w.geometry) < 2:
                    return (0, 0)
                if isinstance(w.geometry[0], list):
                    return (w.geometry[0][1], w.geometry[0][0])
                else:
                    return (w.geometry[1], w.geometry[0])
            sorted_words = sorted(words, key=get_coords)
            lines = []
            current_line = []
            current_y = None
            for word in sorted_words:
                if not word.geometry or len(word.geometry) < 2:
                    continue
                word_y = word.geometry[1] if not isinstance(word.geometry[0], list) else word.geometry[0][1]
                if current_y is None or abs(word_y - current_y) > y_tolerance:
                    if current_line:
                        lines.append(current_line)
                    current_line = []
                    current_y = word_y
                current_line.append({"value": word.text, "confidence": word.confidence, "geometry": word.geometry})
            if current_line:
                lines.append(current_line)
            return lines
        
        ocr_data = {"doc_id": str(document.id), "pages": []}
        for page in document.pages:
            lines = group_words_into_lines(page.words)
            ocr_data["pages"].append({
                "page_idx": page.page_number,
                "dimensions": page.dimensions,
                "blocks": [{"lines": [{"words": line} for line in lines]}] if lines else []
            })
        
        # Apply ALL corrections (document + global)
        doc_corrections = db.query(models.Correction).filter(
            models.Correction.document_id == doc_id
        ).order_by(models.Correction.timestamp.desc()).all()
        
        global_corrections = db.query(models.Correction).filter(
            models.Correction.document_id != doc_id
        ).order_by(models.Correction.timestamp.desc()).all()
        
        all_corrections = doc_corrections + global_corrections
        
        if all_corrections:
            logger.info(f"Applying {len(doc_corrections)} doc + {len(global_corrections)} global corrections")
            ocr_data = apply_corrections_to_ocr_data(ocr_data, all_corrections)
        
        return JSONResponse(content={
            "status": "success",
            "ocrData": ocr_data
        })
    except Exception as e:
        logger.error(f"Error updating OCR data: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/documents/list")
async def get_documents_list(db: Session = Depends(get_db)):
    """Get list of all processed documents from the database."""
    try:
        documents = db.query(models.Document).order_by(models.Document.upload_date.desc()).all()
        return {"documents": [{"id": str(d.id), "filename": d.filename, "processed_at": d.upload_date.isoformat(), "quality_score": d.quality_score, "document_type": d.document_type} for d in documents], "total": len(documents)}
    except Exception as e:
        logger.error(f"Error getting documents list: {e}")
        return {"error": str(e)}, 500

@app.get("/data/outputs/{filename}")
async def serve_output_image(filename: str):
    """Serve output images from the outputs directory."""
    file_path = OUTPUT_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "Image not found"})

@app.get("/raw_ocr/{doc_id}")
async def get_raw_ocr(doc_id: str, db: Session = Depends(get_db)):
    """Get raw OCR data for a document."""
    try:
        document = db.query(models.Document).filter(models.Document.id == doc_id).first()
        if not document:
            return JSONResponse(status_code=404, content={"error": "Document not found"})
        
        # Helper function to group words into lines
        def group_words_into_lines(words, y_tolerance=0.015):
            """Group words by Y-coordinate (normalized 0-1 range)."""
            if not words:
                return []
            
            # Geometry can be either [x, y] or [[x1, y1], [x2, y2]]
            def get_coords(w):
                if not w.geometry or len(w.geometry) < 2:
                    return (0, 0)
                if isinstance(w.geometry[0], list):
                    return (w.geometry[0][1], w.geometry[0][0])  # Y, X from bounding box
                else:
                    return (w.geometry[1], w.geometry[0])  # Y is at index 1, X at index 0
            
            sorted_words = sorted(words, key=get_coords)
            
            lines = []
            current_line = []
            current_y = None
            
            for word in sorted_words:
                if not word.geometry or len(word.geometry) < 2:
                    continue
                # Get Y coordinate
                word_y = word.geometry[1] if not isinstance(word.geometry[0], list) else word.geometry[0][1]
                if current_y is None or abs(word_y - current_y) > y_tolerance:
                    if current_line:
                        lines.append(current_line)
                    current_line = []
                    current_y = word_y
                current_line.append({"value": word.text, "confidence": word.confidence, "geometry": word.geometry})
            if current_line:
                lines.append(current_line)
            return lines
        
        # Reconstruct OCR data from database
        pages = db.query(models.Page).filter(models.Page.document_id == doc_id).order_by(models.Page.page_number).all()
        ocr_data = {"pages": []}
        
        for page in pages:
            words = db.query(models.Word).filter(models.Word.page_id == page.id).all()
            lines = group_words_into_lines(words)
            page_data = {
                "page_idx": page.page_number,
                "dimensions": page.dimensions,
                "blocks": [{"lines": [{"words": line} for line in lines]}] if lines else []
            }
            ocr_data["pages"].append(page_data)
        
        # Load and apply corrections (sorted by timestamp DESC - latest first)
        # Apply ALL corrections globally, not just document-specific
        try:
            doc_corrections = db.query(models.Correction).filter(
                models.Correction.document_id == doc_id
            ).order_by(models.Correction.timestamp.desc()).all()
            
            global_corrections = db.query(models.Correction).filter(
                models.Correction.document_id != doc_id
            ).order_by(models.Correction.timestamp.desc()).all()
            
            all_corrections = doc_corrections + global_corrections
            
            if all_corrections:
                logger.info(f"Applying {len(doc_corrections)} document + {len(global_corrections)} global corrections to raw OCR")
                ocr_data = apply_corrections_to_ocr_data(ocr_data, all_corrections)
        except Exception as e:
            logger.error(f"Error applying corrections to raw OCR: {e}")
            import traceback
            traceback.print_exc()
        
        # Return with cache-busting headers
        return JSONResponse(
            content=ocr_data,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"Error getting raw OCR: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/document_corrections/{doc_id}")
async def get_document_corrections(doc_id: str, db: Session = Depends(get_db)):
    """Get all corrections for a specific document."""
    try:
        # Convert doc_id to UUID for query
        from uuid import UUID
        try:
            doc_uuid = UUID(doc_id)
        except ValueError:
            return {"corrections": [], "total": 0}  # Invalid UUID format
        
        corrections = db.query(models.Correction).filter(
            models.Correction.document_id == doc_uuid
        ).order_by(models.Correction.timestamp.desc()).all()
        
        return {
            "corrections": [
                {
                    "id": str(c.id),
                    "word_id": str(c.word_id) if c.word_id else None,
                    "original_text": c.original_text,
                    "corrected_text": c.corrected_text,
                    "context": c.context,
                    "timestamp": c.timestamp.isoformat() if c.timestamp else None
                }
                for c in corrections
            ],
            "total": len(corrections)
        }
    except Exception as e:
        logger.error(f"Error getting document corrections for {doc_id}: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e), "doc_id": doc_id})

@app.get("/api/config")
async def get_config_api():
    """Get application configuration."""
    try:
        config_manager = get_config()
        # Return the config dict, not the ConfigManager object
        return config_manager.config
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/models/available")
async def get_available_models(db: Session = Depends(get_db)):
    """Get list of available trained models."""
    try:
        models_list = db.query(models.DeployedModel).order_by(
            models.DeployedModel.deployment_date.desc()
        ).all()
        
        return {
            "models": [
                {
                    "id": str(m.id),
                    "model_name": m.model_name,
                    "deployment_date": m.deployment_date.isoformat() if m.deployment_date else None,
                    "accuracy": m.accuracy,
                    "is_active": m.is_active
                }
                for m in models_list
            ],
            "total": len(models_list)
        }
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        return {"models": [], "total": 0}

@app.get("/api/models/deployment-history")
async def get_deployment_history(db: Session = Depends(get_db)):
    """Get model deployment history."""
    try:
        reports = db.query(models.TrainingReport).order_by(
            models.TrainingReport.created_at.desc()
        ).limit(20).all()
        
        return {
            "history": [
                {
                    "id": str(r.id),
                    "training_id": r.training_id,
                    "base_model": r.base_model,
                    "new_model_name": r.new_model_name,
                    "metrics": r.metrics,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in reports
            ],
            "total": len(reports)
        }
    except Exception as e:
        logger.error(f"Error getting deployment history: {e}")
        return {"history": [], "total": 0}

@app.get("/api/document_classification/{doc_id}")
async def get_document_classification(doc_id: str, db: Session = Depends(get_db)):
    """Get document classification/type information."""
    try:
        document = db.query(models.Document).filter(models.Document.id == doc_id).first()
        
        if not document:
            return JSONResponse(status_code=404, content={"error": "Document not found"})
        
        # Return classification data
        return {
            "document_id": str(document.id),
            "document_type": document.document_type or "unknown",
            "classification_confidence": 0.0,  # Can be enhanced with actual classifier
            "filename": document.filename,
            "status": document.status,
            "quality_score": document.quality_score
        }
    except Exception as e:
        logger.error(f"Error getting document classification: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
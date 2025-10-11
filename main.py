
import os
import uuid
import json
from pathlib import Path
import shutil
from typing import Dict, List

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
from classification.document_classifier import get_document_classifier
from config_manager import get_config
from ocr.lexicon_processor import get_lexicon_processor

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
        
        # Step 2.5: Document Classification
        document_classifier = get_document_classifier()
        document_type, classification_confidence = document_classifier.classify_document(ocr_data, layout_data)
        logger.info(f"Document classified as '{document_type}' with confidence {classification_confidence:.3f}")
        
        # Step 2.6: Apply Lexicon Auto-Corrections
        logger.info(f"🧠 Applying lexicon auto-corrections for document type: {document_type}")
        
        try:
            config = get_config()
            lexicon_processor = get_lexicon_processor(config)
            
            # Debug: Show what's in the lexicon
            lexicon = lexicon_processor._load_lexicon(document_type)
            logger.info(f"📚 Loaded lexicon with {len(lexicon)} patterns for type '{document_type}'")
            
            # Show sample patterns for debugging
            if lexicon:
                sample_patterns = list(lexicon.items())[:3]
                for original, corrected in sample_patterns:
                    logger.info(f"   Pattern: '{original}' -> '{corrected}'")
            
            # Apply corrections
            ocr_data, applied_corrections = lexicon_processor.apply_lexicon_corrections(ocr_data, document_type)
            
            if applied_corrections:
                logger.info(f"✅ Applied {len(applied_corrections)} lexicon auto-corrections:")
                for correction in applied_corrections:
                    logger.info(f"   {correction}")
                
                # CRITICAL: Save the auto-corrected OCR data immediately
                with ocr_output_path.open("w", encoding="utf-8") as f:
                    json.dump(ocr_data, f, ensure_ascii=False, indent=2)
                logger.info(f"💾 Saved auto-corrected OCR data to {ocr_output_path}")
            else:
                logger.info("ℹ️ No lexicon auto-corrections applied - no matching patterns found")
                
        except Exception as e:
            logger.error(f"❌ Lexicon auto-correction failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Step 3: Enhanced Field Extraction (Anchor-based + Regex)
        anchor_extractor = get_anchor_extractor()
        anchored_fields = anchor_extractor.extract_anchored_fields(ocr_data)
        
        # Combine with traditional regex extraction (now with document type awareness)
        full_text = " ".join(
            word['value'] 
            for page in ocr_data.get('pages', [])
            for block in page.get('blocks', [])
            for line in block.get('lines', [])
            for word in line.get('words', [])
        )
        regex_fields = normalize_text(full_text, document_type)
        
        # Merge extraction results (anchored fields take precedence)
        extracted_fields = {**regex_fields, **anchored_fields}
        
        # Save enhanced extraction results with document type and auto-corrections
        extracted_fields["document_type"] = document_type
        extracted_fields["classification_confidence"] = classification_confidence
        extracted_fields["auto_corrections_applied"] = applied_corrections
        
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

@app.get("/api/lexicon")
async def get_lexicon_data():
    """Get current lexicon data for review."""
    try:
        lexicon_path = Path("data/lexicons/auto_corrections.json")
        frequency_path = Path("data/lexicons/correction_frequency.json")
        
        lexicon_data = {}
        frequency_data = {}
        
        if lexicon_path.exists():
            with lexicon_path.open("r", encoding="utf-8") as f:
                lexicon_data = json.load(f)
        
        if frequency_path.exists():
            with frequency_path.open("r", encoding="utf-8") as f:
                frequency_data = json.load(f)
        
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
async def get_training_data_stats():
    """Get statistics about training data preparation."""
    try:
        training_dir = Path("data/training_data/ocr_samples")
        
        if not training_dir.exists():
            return JSONResponse(content={
                "total_samples": 0,
                "by_document": {},
                "recent_samples": []
            })
        
        # Count samples by document
        samples_by_doc = {}
        recent_samples = []
        
        for metadata_file in training_dir.glob("*.json"):
            try:
                with metadata_file.open("r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                doc_id = metadata.get("document_id", "unknown")
                samples_by_doc[doc_id] = samples_by_doc.get(doc_id, 0) + 1
                
                # Add to recent samples (keep last 10)
                recent_samples.append({
                    "document_id": doc_id,
                    "original_text": metadata.get("original_text", ""),
                    "corrected_text": metadata.get("corrected_text", ""),
                    "timestamp": metadata.get("timestamp", ""),
                    "image_filename": metadata.get("image_filename", "")
                })
                
            except Exception as e:
                logger.warning(f"Failed to read training metadata {metadata_file}: {e}")
                continue
        
        # Sort recent samples by timestamp and keep last 10
        recent_samples.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        recent_samples = recent_samples[:10]
        
        return JSONResponse(content={
            "total_samples": sum(samples_by_doc.values()),
            "by_document": samples_by_doc,
            "recent_samples": recent_samples
        })
        
    except Exception as e:
        logger.error(f"Failed to get training data stats: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve training data stats"})

@app.post("/api/retrain_stub")
async def trigger_retraining_stub():
    """Stub endpoint for triggering OCR model retraining."""
    try:
        training_dir = Path("data/training_data/ocr_samples")
        
        # Count available training samples
        sample_count = len(list(training_dir.glob("*.json"))) if training_dir.exists() else 0
        
        logger.info(f"🔄 RETRAINING REQUEST: {sample_count} samples available")
        
        if sample_count < 10:
            logger.warning(f"⚠️ Insufficient samples for retraining: {sample_count}/10")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Insufficient training data",
                    "message": f"Need at least 10 samples, found {sample_count}",
                    "samples_available": sample_count,
                    "is_stub": True
                }
            )
        
        # Log all samples being used
        logger.info(f"📚 Using {sample_count} training samples for retraining:")
        json_files = list(training_dir.glob("*.json"))
        for idx, json_file in enumerate(json_files[:5], 1):  # Log first 5
            try:
                with json_file.open('r') as f:
                    sample = json.load(f)
                logger.info(f"   {idx}. '{sample.get('original_text')}' → '{sample.get('corrected_text')}'")
            except:
                pass
        if sample_count > 5:
            logger.info(f"   ... and {sample_count - 5} more samples")
        
        # Create a stub retraining log
        models_dir = Path("models/ocr_weights")
        models_dir.mkdir(parents=True, exist_ok=True)
        
        logger.warning("⚠️ STUB IMPLEMENTATION: This is a simulation, not real retraining!")
        logger.info("💡 Real retraining would:")
        logger.info("   1. Load DocTR model weights")
        logger.info("   2. Fine-tune on training samples")
        logger.info("   3. Validate accuracy improvement")
        logger.info("   4. Save updated model")
        
        retraining_log = {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "samples_used": sample_count,
            "status": "completed_stub",
            "model_version": "v1.0_stub",
            "is_stub": True,
            "notes": "⚠️ STUB: This is a simulation. Real retraining would fine-tune DocTR model on the collected samples.",
            "next_steps": [
                "Implement PyTorch fine-tuning pipeline",
                "Load DocTR pre-trained weights",
                "Create training loop with samples",
                "Validate on test set",
                "Save and deploy improved model"
            ]
        }
        
        log_path = models_dir / f"retraining_log_{__import__('datetime').datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with log_path.open("w", encoding="utf-8") as f:
            json.dump(retraining_log, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Retraining stub completed - log saved to: {log_path}")
        
        return JSONResponse(content={
            "status": "success",
            "message": "⚠️ Retraining Simulation Completed (This is a STUB - no actual model update)",
            "samples_used": sample_count,
            "model_version": "v1.0_stub",
            "log_file": str(log_path),
            "is_stub": True,
            "warning": "This is a simulation. The OCR model has NOT been actually retrained. Training samples are collected and ready for real implementation."
        })
        
    except Exception as e:
        logger.error(f"❌ Retraining stub failed: {e}")
        return JSONResponse(status_code=500, content={"error": f"Retraining failed: {str(e)}", "is_stub": True})


@app.post("/api/retrain_real")
async def trigger_real_retraining(
    epochs: int = Form(20),
    batch_size: int = Form(16),
    learning_rate: float = Form(0.001)
):
    """Real OCR model retraining endpoint using PyTorch."""
    try:
        from training.train_service import TrainingService
        
        logger.info("=" * 60)
        logger.info("🚀 REAL OCR MODEL RETRAINING REQUESTED")
        logger.info("=" * 60)
        logger.info(f"Parameters:")
        logger.info(f"  Epochs: {epochs}")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Learning rate: {learning_rate}")
        
        # Initialize training service
        service = TrainingService()
        
        # Check if training can proceed
        can_train, message = service.can_train(min_samples=10)
        sample_count = service.count_samples()
        
        if not can_train:
            logger.warning(f"⚠️ {message}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Insufficient training data",
                    "message": message,
                    "samples_available": sample_count,
                    "is_stub": False
                }
            )
        
        logger.info(f"✅ {message}")
        logger.info(f"🎓 Starting real model training...")
        
        # Train the model (this will take time)
        report = service.train_model(
            num_epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            val_ratio=0.2
        )
        
        logger.info("=" * 60)
        logger.info("✅ TRAINING COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info(f"Final train loss: {report['final_train_loss']:.4f}")
        if report['final_val_accuracy']:
            logger.info(f"Final val accuracy: {report['final_val_accuracy']:.2%}")
        logger.info(f"Model saved to: {report['model_path']}")
        
        return JSONResponse(content={
            "status": "success",
            "message": "✅ Real OCR Model Training Completed!",
            "is_stub": False,
            "samples_used": report['samples_used'],
            "train_samples": report['train_samples'],
            "val_samples": report['val_samples'],
            "epochs_completed": report['epochs'],
            "final_train_loss": float(report['final_train_loss']),
            "final_val_loss": float(report['final_val_loss']) if report['final_val_loss'] else None,
            "final_val_accuracy": float(report['final_val_accuracy']) if report['final_val_accuracy'] else None,
            "best_val_accuracy": float(report['best_val_accuracy']) if report['best_val_accuracy'] else None,
            "model_path": report['model_path'],
            "device": report['device'],
            "vocab_size": report['vocab_size']
        })
        
    except ImportError as e:
        logger.error(f"❌ Training module not available: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Training module not available",
                "message": "PyTorch training dependencies not installed. Install with: pip install torch torchvision",
                "is_stub": False
            }
        )
    except Exception as e:
        logger.error(f"❌ Real retraining failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Real retraining failed: {str(e)}",
                "is_stub": False
            }
        )


@app.get("/api/models/available")
async def get_available_models():
    """List all trained models available for deployment."""
    try:
        from training.model_deployment import ModelDeploymentManager
        
        manager = ModelDeploymentManager()
        models = manager.list_available_models()
        active = manager.get_active_model_info()
        
        return JSONResponse(content={
            "status": "success",
            "available_models": models,
            "active_model": active,
            "total_models": len(models)
        })
    except ImportError:
        return JSONResponse(
            status_code=500,
            content={"error": "Deployment module not available"}
        )
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to list models: {str(e)}"}
        )


@app.post("/api/models/deploy")
async def deploy_model(
    model_filename: str = Form(...),
    deployed_by: str = Form("user"),
    notes: str = Form("")
):
    """Deploy a trained model to production."""
    try:
        from training.model_deployment import ModelDeploymentManager
        
        logger.info(f"🚀 Deployment request: {model_filename} by {deployed_by}")
        
        manager = ModelDeploymentManager()
        result = manager.deploy_model(model_filename, deployed_by, notes)
        
        return JSONResponse(content=result)
        
    except ImportError:
        return JSONResponse(
            status_code=500,
            content={"error": "Deployment module not available"}
        )
    except FileNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": str(e)}
        )
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": f"Deployment failed: {str(e)}"}
        )


@app.post("/api/models/rollback")
async def rollback_model():
    """Rollback to the previous deployed model."""
    try:
        from training.model_deployment import ModelDeploymentManager
        
        logger.info("🔄 Rollback request")
        
        manager = ModelDeploymentManager()
        result = manager.rollback_to_previous()
        
        return JSONResponse(content=result)
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Rollback failed: {str(e)}"}
        )


@app.get("/api/models/deployment-history")
async def get_deployment_history(limit: int = 10):
    """Get model deployment history."""
    try:
        from training.model_deployment import ModelDeploymentManager
        
        manager = ModelDeploymentManager()
        history = manager.get_deployment_history(limit)
        
        return JSONResponse(content={
            "status": "success",
            "history": history,
            "total_records": len(history)
        })
        
    except Exception as e:
        logger.error(f"Failed to get deployment history: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get history: {str(e)}"}
        )


@app.get("/api/document_types")
async def get_document_types():
    """Get available document types and their characteristics."""
    try:
        classifier = get_document_classifier()
        types_info = classifier.list_types()
        
        return JSONResponse(content={
            "document_types": types_info,
            "total_types": len(types_info)
        })
        
    except Exception as e:
        logger.error(f"Failed to get document types: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve document types"})

@app.get("/api/document_classification/{doc_id}")
async def get_document_classification(doc_id: str):
    """Get classification information for a specific document."""
    try:
        extracted_path = OUTPUT_DIR / f"{doc_id}_extracted.json"
        if not extracted_path.exists():
            return JSONResponse(status_code=404, content={"error": "Document classification not found"})
        
        with extracted_path.open("r", encoding="utf-8") as f:
            extracted_data = json.load(f)
        
        classification_info = {
            "document_type": extracted_data.get("document_type", "unknown"),
            "classification_confidence": extracted_data.get("classification_confidence", 0.0),
            "document_id": doc_id
        }
        
        # Add type description if available
        classifier = get_document_classifier()
        type_info = classifier.get_type_info(classification_info["document_type"])
        if type_info:
            classification_info["type_description"] = type_info.description
            classification_info["type_keywords"] = type_info.keywords
        
        return JSONResponse(content=classification_info)
        
    except Exception as e:
        logger.error(f"Failed to get document classification: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve document classification"})

@app.get("/api/document_corrections/{doc_id}")
async def get_document_corrections(doc_id: str):
    """Get correction statistics and auto-corrections applied for a specific document."""
    try:
        corrections_dir = Path("data/logs/corrections")
        corrections_file = corrections_dir / f"{doc_id}.json"
        
        stats = {
            "document_id": doc_id,
            "total_corrections": 0,
            "corrections": [],
            "auto_corrections_applied": 0,
            "lexicon_patterns_used": []
        }
        
        # Load corrections for this document
        if corrections_file.exists():
            with corrections_file.open("r", encoding="utf-8") as f:
                corrections_data = json.load(f)
                stats["corrections"] = corrections_data.get("corrections", [])
                stats["total_corrections"] = len(stats["corrections"])
        
        # Check what auto-corrections were applied during OCR processing
        extracted_path = OUTPUT_DIR / f"{doc_id}_extracted.json"
        if extracted_path.exists():
            with extracted_path.open("r", encoding="utf-8") as f:
                extracted_data = json.load(f)
                corrections_applied = extracted_data.get("corrections_applied", [])
                stats["auto_corrections_applied"] = len(corrections_applied)
                stats["lexicon_patterns_used"] = corrections_applied
        
        return JSONResponse(content=stats)
        
    except Exception as e:
        logger.error(f"Failed to get document corrections: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve document corrections"})

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
    original_text: str = Form(...),
    corrected_text: str = Form(...),
    true_original_text: str = Form(""),  # True original OCR text for lexicon learning
    corrected_bbox: str = Form(...),
    user_id: str = Form("analyst1")
):
    """Simplified, bulletproof correction saving."""
    logger.info(f"🔧 SAVE_CORRECTION START: doc_id={doc_id}")
    logger.info(f"   word_id={word_id}, page={page}")
    logger.info(f"   current_displayed='{original_text}'")
    logger.info(f"   new_correction='{corrected_text}'")
    logger.info(f"   true_original_ocr='{true_original_text}'")
    
    # Determine which text to use for lexicon learning
    text_for_lexicon = true_original_text if true_original_text else original_text
    logger.info(f"📚 Using for lexicon learning: '{text_for_lexicon}' -> '{corrected_text}'")
    
    try:
        # Basic validation
        if not doc_id or not word_id or not original_text or not corrected_text:
            logger.error("❌ Missing required parameters")
            return JSONResponse(status_code=400, content={"error": "Missing required parameters"})
        
        if original_text == corrected_text:
            logger.info("ℹ️ No change in text - skipping save")
            return JSONResponse(content={"status": "success", "message": "No change detected"})
        
        # Parse bbox
        try:
            bbox = json.loads(corrected_bbox)
            logger.info(f"   bbox parsed: {bbox}")
        except Exception as e:
            logger.error(f"❌ Invalid bbox format: {e}")
            return JSONResponse(status_code=400, content={"error": "Invalid bbox format"})

        # Simple correction log entry
        import datetime
        log_entry = {
            "document_id": doc_id,
            "page": page,
            "word_id": word_id,
            "original_text": original_text,
            "corrected_text": corrected_text,
            "corrected_bbox": bbox,
            "user_id": user_id,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        
        logger.info(f"📝 Created log entry: {log_entry}")

        # Save to corrections directory
        corrections_dir = Path("data/logs/corrections")
        corrections_dir.mkdir(parents=True, exist_ok=True)
        log_path = corrections_dir / f"{doc_id}.json"
        
        # Load existing corrections
        try:
            if log_path.exists():
                with log_path.open("r", encoding="utf-8") as f:
                    corrections_data = json.load(f)
                logger.info(f"📂 Loaded existing corrections: {len(corrections_data.get('corrections', []))}")
            else:
                corrections_data = {"corrections": [], "document_id": doc_id}
                logger.info(f"📂 Creating new corrections file")
        except Exception as e:
            logger.error(f"❌ Failed to load corrections file: {e}")
            corrections_data = {"corrections": [], "document_id": doc_id}
        
        # Add new correction
        corrections_data["corrections"].append(log_entry)
        logger.info(f"📝 Added correction - total now: {len(corrections_data['corrections'])}")
        
        # Save corrections file
        try:
            with log_path.open("w", encoding="utf-8") as f:
                json.dump(corrections_data, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Saved corrections to: {log_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save corrections file: {e}")
            return JSONResponse(status_code=500, content={"error": f"Failed to save corrections: {e}"})

        # Simple lexicon update
        lexicon_updated = False
        try:
            lexicon_dir = Path("data/lexicons")
            lexicon_dir.mkdir(parents=True, exist_ok=True)
            
            # Update frequency
            frequency_file = lexicon_dir / "correction_frequency.json"
            try:
                if frequency_file.exists():
                    with frequency_file.open("r", encoding="utf-8") as f:
                        frequency_data = json.load(f)
                else:
                    frequency_data = {}
            except:
                frequency_data = {}
            
            # Use current displayed text for immediate tracking
            correction_key = f"{original_text} -> {corrected_text}"
            frequency_data[correction_key] = frequency_data.get(correction_key, 0) + 1
            current_frequency = frequency_data[correction_key]
            
            with frequency_file.open("w", encoding="utf-8") as f:
                json.dump(frequency_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📊 Updated frequency: {correction_key} = {current_frequency}")
            
            # ALWAYS update lexicon - use true original text for learning
            lexicon_file = lexicon_dir / "auto_corrections.json"
            try:
                if lexicon_file.exists():
                    with lexicon_file.open("r", encoding="utf-8") as f:
                        lexicon_data = json.load(f)
                else:
                    lexicon_data = {}
            except:
                lexicon_data = {}
            
            # CRITICAL FIX: Always update lexicon with the latest correction
            # Use true original text -> latest correction for the lexicon pattern
            if text_for_lexicon in lexicon_data:
                old_correction = lexicon_data[text_for_lexicon]
                if old_correction != corrected_text:
                    lexicon_data[text_for_lexicon] = corrected_text
                    lexicon_updated = True
                    logger.info(f"🔄 UPDATED existing lexicon pattern:")
                    logger.info(f"   Pattern key: '{text_for_lexicon}'")
                    logger.info(f"   Old correction: '{old_correction}'")
                    logger.info(f"   NEW correction: '{corrected_text}' ⭐")
                else:
                    logger.info(f"ℹ️ Lexicon pattern unchanged: '{text_for_lexicon}' -> '{corrected_text}'")
            else:
                # New pattern - add to lexicon
                lexicon_data[text_for_lexicon] = corrected_text
                lexicon_updated = True
                logger.info(f"✅ ADDED new lexicon pattern:")
                logger.info(f"   Pattern: '{text_for_lexicon}' -> '{corrected_text}' ⭐")
            
            if lexicon_updated:
                with lexicon_file.open("w", encoding="utf-8") as f:
                    json.dump(lexicon_data, f, ensure_ascii=False, indent=2)
                logger.info(f"💾 Lexicon saved with {len(lexicon_data)} total patterns")
                logger.info(f"🎯 LATEST CORRECTION SAVED: '{text_for_lexicon}' -> '{corrected_text}'")
            
        except Exception as e:
            logger.warning(f"⚠️ Lexicon update failed but correction saved: {e}")

        # Prepare training data (background task - won't block response)
        training_data_prepared = False
        try:
            import asyncio
            asyncio.create_task(
                prepare_training_data_async(
                    doc_id=doc_id,
                    page=page,
                    word_id=word_id,
                    original_text=text_for_lexicon,
                    corrected_text=corrected_text,
                    bbox=bbox
                )
            )
            training_data_prepared = True
            logger.info(f"🎓 Training data preparation task created for word {word_id}")
        except Exception as e:
            logger.warning(f"⚠️ Training data preparation failed (non-blocking): {e}")

        # Return success response
        message = "Correction saved successfully"
        if lexicon_updated:
            if original_text in lexicon_data and len([k for k in lexicon_data.keys() if k == original_text]) > 0:
                message += " - Lexicon pattern updated"
            else:
                message += " - Added to lexicon"
        
        if training_data_prepared:
            message += " - Training sample created"
        
        response_data = {
            "status": "success", 
            "message": message,
            "lexicon_updated": lexicon_updated,
            "training_data_prepared": training_data_prepared,
            "correction_frequency": current_frequency if 'current_frequency' in locals() else 1,
            "lexicon_size": len(lexicon_data) if 'lexicon_data' in locals() else 0
        }
        
        logger.info(f"✅ SAVE_CORRECTION SUCCESS: {response_data}")
        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"❌ SAVE_CORRECTION FAILED: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": f"Save failed: {str(e)}"})

@app.post("/update_ocr_data/{doc_id}")
async def update_ocr_data_realtime(
    doc_id: str,
    word_id: str = Form(...),
    corrected_text: str = Form(...),
    page_index: int = Form(...)
):
    """Update OCR data in real-time when user makes corrections."""
    try:
        ocr_json_path = OUTPUT_DIR / f"{doc_id}.json"
        if not ocr_json_path.exists():
            return JSONResponse(status_code=404, content={"error": "OCR data not found"})
        
        # Load current OCR data
        with ocr_json_path.open("r", encoding="utf-8") as f:
            ocr_data = json.load(f)
        
        # Find and update the specific word
        word_found = False
        word_counter = 0
        
        for page_idx, page in enumerate(ocr_data.get("pages", [])):
            if page_idx != page_index:
                # Skip to correct page and count words
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        word_counter += len(line.get("words", []))
                continue
            
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        current_word_id = f"p{page_idx}_w{word_counter}"
                        if current_word_id == word_id:
                            # Store original value if not already stored
                            if "original_value" not in word:
                                word["original_value"] = word.get("value", "")
                            
                            # Update the word value
                            word["value"] = corrected_text
                            word["corrected"] = True
                            word["manually_corrected"] = True  # Mark as manually corrected
                            word["corrected_at"] = __import__("datetime").datetime.utcnow().isoformat()
                            
                            # If this was auto-corrected, mark it as manually overridden
                            if word.get("auto_corrected") or word.get("corrected_by_lexicon"):
                                word["auto_correction_overridden"] = True
                                logger.info(f"🔄 Auto-correction overridden for word {word_id}: '{word.get('original_value', '')}' -> '{corrected_text}'")
                            
                            word_found = True
                            break
                        word_counter += 1
                    if word_found:
                        break
                if word_found:
                    break
            if word_found:
                break
        
        if not word_found:
            return JSONResponse(status_code=404, content={"error": "Word not found in OCR data"})
        
        # Save updated OCR data
        with ocr_json_path.open("w", encoding="utf-8") as f:
            json.dump(ocr_data, f, ensure_ascii=False, indent=2)
        
        # Also update the raw OCR data
        raw_ocr_data = _extract_raw_ocr_structure(ocr_data, doc_id)
        raw_ocr_output_path = OUTPUT_DIR / f"{doc_id}_raw.json"
        with raw_ocr_output_path.open("w", encoding="utf-8") as f:
            json.dump(raw_ocr_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Updated OCR data for {doc_id}, word {word_id}: '{corrected_text}'")
        
        return JSONResponse(content={
            "status": "success",
            "message": "OCR data updated",
            "word_id": word_id,
            "corrected_text": corrected_text
        })
        
    except Exception as e:
        logger.error(f"Failed to update OCR data: {e}")
        return JSONResponse(status_code=500, content={"error": f"Failed to update OCR data: {str(e)}"})

@app.get("/api/config")
async def get_system_config():
    """Get system configuration settings."""
    try:
        config = get_config()
        return JSONResponse(content={
            "lexicon_learning_threshold": config.get("lexicon_learning_threshold", 3),
            "auto_correction_enabled": config.get("auto_correction_enabled", True),
            "ui_settings": config.get("ui_settings", {}),
            "document_types": {
                doc_type: {
                    "threshold": config.get_learning_threshold(doc_type),
                    "auto_correction_enabled": config.is_auto_correction_enabled(doc_type)
                }
                for doc_type in ["invoice", "receipt", "identity_document", "contract", "bank_statement"]
            }
        })
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to retrieve configuration"})

@app.post("/api/config/update")
async def update_system_config(
    key: str = Form(...),
    value: str = Form(...)
):
    """Update system configuration setting."""
    try:
        config = get_config()
        
        # Parse value based on key type
        if key.endswith("_threshold"):
            parsed_value = int(value)
        elif key.endswith("_enabled"):
            parsed_value = value.lower() in ("true", "1", "yes")
        else:
            parsed_value = value
        
        config.update(key, parsed_value)
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Updated {key} to {parsed_value}",
            "key": key,
            "value": parsed_value
        })
        
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return JSONResponse(status_code=500, content={"error": f"Failed to update configuration: {str(e)}"})

@app.get("/export/{doc_id}")
async def export_structured_data(doc_id: str, format: str = "json"):
    """
    Export structured data with applied corrections and enhanced processing.
    Supports multiple formats: json, csv, xml
    """
    ocr_json_path = OUTPUT_DIR / f"{doc_id}.json"
    if not ocr_json_path.exists():
        return JSONResponse(status_code=404, content={"error": "OCR data not found."})

    # Load OCR data (now contains real-time corrections)
    with ocr_json_path.open("r", encoding="utf-8") as f:
        corrected_ocr_data = json.load(f)
    
    # Since we now update OCR data in real-time, we use it directly
    # But still apply any additional corrections from log for completeness
    corrections_log_path = OUTPUT_DIR / f"{doc_id}_corrections.log"
    correction_integrator = get_correction_integrator()
    
    # Apply any remaining corrections that might not be in the OCR data yet
    final_ocr_data, corrected_extracted_fields = correction_integrator.apply_corrections_to_export(
        doc_id, corrected_ocr_data, {}, corrections_log_path
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
            for page in final_ocr_data.get('pages', [])
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
                        "confidence": round(float(confidence), 4) if confidence else 0.0,
                        "auto_corrected": word.get("auto_corrected", False),
                        "corrected_by_lexicon": word.get("corrected_by_lexicon", False),
                        "original_value": word.get("original_value", "")
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

# --- Enhanced Correction System Helper Functions ---

async def update_lexicon_async(original_text: str, corrected_text: str, doc_id: str, document_type: str = "document") -> Dict:
    """
    Update lexicon learning system based on correction patterns.
    Returns dictionary with update information.
    """
    try:
        import asyncio
        
        logger.info(f"Updating lexicon: '{original_text}' -> '{corrected_text}' (doc_type: {document_type})")
        
        lexicon_dir = Path("data/lexicons")
        lexicon_dir.mkdir(parents=True, exist_ok=True)
        
        # Load global correction frequency
        frequency_file = lexicon_dir / "correction_frequency.json"
        try:
            if frequency_file.exists():
                with frequency_file.open("r", encoding="utf-8") as f:
                    frequency_data = json.load(f)
            else:
                frequency_data = {}
        except Exception as e:
            logger.warning(f"Failed to load frequency data: {e}")
            frequency_data = {}
        
        # Track this correction
        correction_key = f"{original_text} -> {corrected_text}"
        frequency_data[correction_key] = frequency_data.get(correction_key, 0) + 1
        current_frequency = frequency_data[correction_key]
        
        logger.info(f"Correction frequency updated: {correction_key} = {current_frequency}")
        
        # Save updated frequency
        try:
            with frequency_file.open("w", encoding="utf-8") as f:
                json.dump(frequency_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save frequency data: {e}")
        
        # Load current lexicon
        lexicon_file = lexicon_dir / "auto_corrections.json"
        try:
            if lexicon_file.exists():
                with lexicon_file.open("r", encoding="utf-8") as f:
                    lexicon_data = json.load(f)
            else:
                lexicon_data = {}
        except Exception as e:
            logger.warning(f"Failed to load lexicon data: {e}")
            lexicon_data = {}
        
        lexicon_updated = False
        
        # Get configurable learning threshold - simplified to avoid config issues
        try:
            config = get_config()
            learning_threshold = config.get_learning_threshold(document_type)
        except Exception as e:
            logger.warning(f"Config error, using default threshold: {e}")
            learning_threshold = 1  # Default threshold
        
        logger.info(f"Using learning threshold: {learning_threshold}")
        
        # Check if this correction should be added to lexicon
        if current_frequency >= learning_threshold:
            if original_text not in lexicon_data:
                # New pattern - add to lexicon
                lexicon_data[original_text] = corrected_text
                lexicon_updated = True
                logger.info(f"✅ Added NEW pattern to lexicon: '{original_text}' -> '{corrected_text}' (frequency: {current_frequency})")
            elif lexicon_data[original_text] != corrected_text:
                # Existing pattern but different correction - update it
                old_correction = lexicon_data[original_text]
                lexicon_data[original_text] = corrected_text
                lexicon_updated = True
                logger.info(f"🔄 Updated lexicon pattern: '{original_text}' from '{old_correction}' to '{corrected_text}'")
            
            if lexicon_updated:
                try:
                    with lexicon_file.open("w", encoding="utf-8") as f:
                        json.dump(lexicon_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"💾 Lexicon saved with {len(lexicon_data)} patterns")
                except Exception as e:
                    logger.error(f"Failed to save lexicon: {e}")
                    lexicon_updated = False
        
        result = {
            "updated": lexicon_updated,
            "frequency": current_frequency,
            "lexicon_size": len(lexicon_data),
            "correction_key": correction_key
        }
        
        logger.info(f"Lexicon update complete: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to update lexicon: {e}")
        import traceback
        logger.error(f"Lexicon update traceback: {traceback.format_exc()}")
        return {
            "updated": False,
            "frequency": 0,
            "lexicon_size": 0,
            "correction_key": f"{original_text} -> {corrected_text}"
        }

async def prepare_training_data_async(doc_id: str, page: int, word_id: str, 
                                    original_text: str, corrected_text: str, bbox: List[float]):
    """
    Prepare training data by cropping word regions from images.
    Made more robust to prevent blocking the correction save process.
    """
    try:
        logger.info(f"Starting training data preparation for word {word_id}")
        
        # Find the page image
        page_image_path = OUTPUT_DIR / f"{doc_id}_page_{page}.png"
        if not page_image_path.exists():
            # Try page 0 as fallback
            page_image_path = OUTPUT_DIR / f"{doc_id}_page_0.png"
        
        if not page_image_path.exists():
            logger.warning(f"Page image not found for training data: {page_image_path}")
            return
        
        # Create training data directory
        training_dir = Path("data/training_data/ocr_samples")
        training_dir.mkdir(parents=True, exist_ok=True)
        
        # Handle bbox format - could be DocTR format [[x1,y1], [x2,y2]] or our format [x1,y1,x2,y2]
        if len(bbox) == 2 and isinstance(bbox[0], list):
            # DocTR format: [[x1, y1], [x2, y2]]
            x1, y1 = bbox[0]
            x2, y2 = bbox[1]
        elif len(bbox) == 4:
            # Our format: [x1, y1, x2, y2]
            x1, y1, x2, y2 = bbox
        else:
            logger.warning(f"Invalid bbox format for training data: {bbox}")
            return
        
        # Quick training data preparation without complex image processing
        try:
            from PIL import Image
            
            with Image.open(page_image_path) as img:
                # Convert relative coordinates to absolute
                img_width, img_height = img.size
                
                # Convert from relative [0,1] to absolute coordinates
                abs_x1 = max(0, int(x1 * img_width) - 5)
                abs_y1 = max(0, int(y1 * img_height) - 5)
                abs_x2 = min(img_width, int(x2 * img_width) + 5)
                abs_y2 = min(img_height, int(y2 * img_height) + 5)
                
                # Crop the word region
                word_image = img.crop((abs_x1, abs_y1, abs_x2, abs_y2))
                
                # Save cropped image
                timestamp = __import__("datetime").datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                image_filename = f"{doc_id}_{word_id}_{timestamp}.png"
                image_path = training_dir / image_filename
                word_image.save(image_path)
                
                # Save simple metadata
                metadata = {
                    "document_id": doc_id,
                    "page": page,
                    "word_id": word_id,
                    "original_text": original_text,
                    "corrected_text": corrected_text,
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat()
                }
                
                metadata_filename = f"{doc_id}_{word_id}_{timestamp}.json"
                metadata_path = training_dir / metadata_filename
                with metadata_path.open("w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                logger.info(f"✅ Training data prepared: {image_filename}")
                
        except ImportError:
            logger.warning("PIL not available - skipping training data image preparation")
        except Exception as e:
            logger.warning(f"Training data image preparation failed: {e}")
        
    except Exception as e:
        logger.warning(f"Training data preparation failed: {e}")
        # Don't let training data failures block correction saving

if __name__ == "__main__":
    import uvicorn
    # To run: uvicorn main:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8000)

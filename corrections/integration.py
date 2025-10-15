"""
Correction integration system that applies logged human corrections to document processing results.
Implements the missing functionality to integrate manual corrections into final export output.
"""

import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Correction:
    """Represents a single correction made by a human reviewer."""
    document_id: str
    page: int
    word_id: str
    original_text: str
    corrected_text: str
    corrected_bbox: List[float]
    user_id: str
    timestamp: datetime
    correction_type: str = "text_edit"  # text_edit, bbox_adjustment, field_relabel

from database.connector import get_db
from database import models
from sqlalchemy.orm import Session
from sqlalchemy import func

@dataclass
class Correction:
    """Represents a single correction made by a human reviewer."""
    document_id: str
    page: int
    word_id: str
    original_text: str
    corrected_text: str
    corrected_bbox: List[float]
    user_id: str
    timestamp: datetime
    correction_type: str = "text_edit"

class CorrectionIntegrator:
    """
    Integrates human corrections into document processing results.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the correction integrator."""
        self.db = db_session
    
    def apply_corrections_to_export(self, 
                                  doc_id: str, 
                                  ocr_data: Dict, 
                                  extracted_fields: Dict) -> Tuple[Dict, Dict]:
        """
        Apply all logged corrections to OCR data and re-extract fields.
        """
        try:
            logger.info(f"Applying corrections for document: {doc_id}")
            
            corrections = self._load_corrections(doc_id)
            
            if not corrections:
                return ocr_data, extracted_fields
            
            corrected_ocr_data = self._apply_corrections_to_ocr(ocr_data, corrections)
            
            corrected_extracted_fields = self._re_extract_fields_from_corrected_data(
                corrected_ocr_data, extracted_fields, corrections
            )
            
            logger.info(f"Applied {len(corrections)} corrections for document: {doc_id}")
            return corrected_ocr_data, corrected_extracted_fields
            
        except Exception as e:
            logger.error(f"Failed to apply corrections for document {doc_id}: {e}")
            return ocr_data, extracted_fields
    
    def _load_corrections(self, doc_id: str) -> List[Correction]:
        """Load corrections from the database for a specific document."""
        db_corrections = self.db.query(models.Correction).filter(models.Correction.document_id == doc_id).all()
        # Convert ORM objects to dataclass objects if needed, or use them directly
        return db_corrections

    # ... other methods like _apply_corrections_to_ocr remain mostly the same, but take DB objects ...

class CorrectionLearner:
    """
    Learns from correction patterns to improve future processing.
    """
    
    def __init__(self, db_session: Session, learning_threshold: int = 3):
        self.db = db_session
        self.learning_threshold = learning_threshold
    
    def update_correction_lexicon(self):
        """Update correction lexicon based on recurring correction patterns in the database."""
        try:
            # Find correction patterns that meet the threshold
            patterns = self.db.query(
                models.Correction.original_text, 
                models.Correction.corrected_text, 
                func.count(models.Correction.id).label('count')
            ).group_by(models.Correction.original_text, models.Correction.corrected_text)\
            .having(func.count(models.Correction.id) >= self.learning_threshold).all()

            updates_made = 0
            for original, corrected, count in patterns:
                lexicon_entry = self.db.query(models.Lexicon).filter(models.Lexicon.misspelled == original).first()
                if lexicon_entry:
                    if lexicon_entry.corrected != corrected:
                        lexicon_entry.corrected = corrected
                        updates_made += 1
                else:
                    new_entry = models.Lexicon(misspelled=original, corrected=corrected, frequency=count)
                    self.db.add(new_entry)
                    updates_made += 1
            
            if updates_made > 0:
                self.db.commit()
                logger.info(f"Updated correction lexicon with {updates_made} new patterns")
            
            return updates_made
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update correction lexicon: {e}")
            return 0

# Global instances
_correction_integrator: Optional[CorrectionIntegrator] = None
_correction_learner: Optional[CorrectionLearner] = None

def get_correction_integrator(db: Session) -> CorrectionIntegrator:
    global _correction_integrator
    if _correction_integrator is None:
        _correction_integrator = CorrectionIntegrator(db)
    return _correction_integrator

def get_correction_learner(db: Session) -> CorrectionLearner:
    global _correction_learner
    if _correction_learner is None:
        _correction_learner = CorrectionLearner(db)
    return _correction_learner

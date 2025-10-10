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

class CorrectionIntegrator:
    """
    Integrates human corrections into document processing results.
    Applies logged corrections to OCR data and field extractions.
    """
    
    def __init__(self):
        """Initialize the correction integrator."""
        self.correction_cache = {}  # Cache for frequently accessed corrections
    
    def apply_corrections_to_export(self, 
                                  doc_id: str, 
                                  ocr_data: Dict, 
                                  extracted_fields: Dict,
                                  corrections_log_path: Path) -> Tuple[Dict, Dict]:
        """
        Apply all logged corrections to OCR data and re-extract fields.
        
        Args:
            doc_id: Document identifier
            ocr_data: Original OCR data from DocTR
            extracted_fields: Original field extraction results
            corrections_log_path: Path to corrections log file
            
        Returns:
            Tuple of (corrected_ocr_data, corrected_extracted_fields)
        """
        try:
            logger.info(f"Applying corrections for document: {doc_id}")
            
            # Load corrections from log
            corrections = self._load_corrections(corrections_log_path, doc_id)
            
            if not corrections:
                logger.info(f"No corrections found for document: {doc_id}")
                return ocr_data, extracted_fields
            
            # Apply corrections to OCR data
            corrected_ocr_data = self._apply_corrections_to_ocr(ocr_data, corrections)
            
            # Re-extract fields from corrected text
            corrected_extracted_fields = self._re_extract_fields_from_corrected_data(
                corrected_ocr_data, extracted_fields, corrections
            )
            
            logger.info(f"Applied {len(corrections)} corrections for document: {doc_id}")
            return corrected_ocr_data, corrected_extracted_fields
            
        except Exception as e:
            logger.error(f"Failed to apply corrections for document {doc_id}: {e}")
            return ocr_data, extracted_fields  # Return original data on error
    
    def _load_corrections(self, corrections_log_path: Path, doc_id: str) -> List[Correction]:
        """Load corrections from log file for a specific document."""
        corrections = []
        
        if not corrections_log_path.exists():
            return corrections
            
        try:
            with corrections_log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        correction_data = json.loads(line)
                        
                        # Only include corrections for this document
                        if correction_data.get("document_id") == doc_id:
                            correction = Correction(
                                document_id=correction_data["document_id"],
                                page=correction_data["page"],
                                word_id=correction_data["word_id"],
                                original_text="",  # We'll get this from OCR data
                                corrected_text=correction_data["corrected_text"],
                                corrected_bbox=correction_data["corrected_bbox"],
                                user_id=correction_data["user_id"],
                                timestamp=datetime.fromisoformat(correction_data["timestamp"]),
                                correction_type=correction_data.get("correction_type", "text_edit")
                            )
                            corrections.append(correction)
                            
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Skipping invalid correction entry: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to load corrections from {corrections_log_path}: {e}")
            
        return corrections
    
    def _apply_corrections_to_ocr(self, ocr_data: Dict, corrections: List[Correction]) -> Dict:
        """Apply text corrections to OCR data structure."""
        corrected_data = json.loads(json.dumps(ocr_data))  # Deep copy
        
        # Create lookup for corrections by word_id
        corrections_by_word_id = {c.word_id: c for c in corrections}
        
        # Apply corrections to OCR structure
        for page_idx, page in enumerate(corrected_data.get("pages", [])):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        # Generate word_id (matching the format used in UI)
                        word_id = f"w{self._get_word_index(corrected_data, page_idx, word)}"
                        
                        if word_id in corrections_by_word_id:
                            correction = corrections_by_word_id[word_id]
                            
                            # Store original text for reference
                            word["original_value"] = word.get("value", "")
                            
                            # Apply correction
                            word["value"] = correction.corrected_text
                            word["corrected"] = True
                            word["corrected_by"] = correction.user_id
                            word["corrected_at"] = correction.timestamp.isoformat()
                            
                            # Update bounding box if provided
                            if correction.corrected_bbox:
                                word["geometry"] = [correction.corrected_bbox]
                                
                            logger.debug(f"Applied correction to word {word_id}: "
                                       f"'{word['original_value']}' -> '{word['value']}'")
        
        return corrected_data
    
    def _get_word_index(self, ocr_data: Dict, target_page: int, target_word: Dict) -> int:
        """Get the global word index for a specific word (matches UI numbering)."""
        word_counter = 0
        
        for page_idx, page in enumerate(ocr_data.get("pages", [])):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        if page_idx == target_page and word is target_word:
                            return word_counter
                        word_counter += 1
                        
        return word_counter
    
    def _re_extract_fields_from_corrected_data(self, 
                                             corrected_ocr_data: Dict,
                                             original_fields: Dict, 
                                             corrections: List[Correction]) -> Dict:
        """Re-extract fields using corrected OCR text."""
        # Import here to avoid circular imports
        from postprocessing.normalize import normalize_text
        
        # Extract corrected full text
        corrected_full_text = " ".join(
            word['value'] 
            for page in corrected_ocr_data.get('pages', [])
            for block in page.get('blocks', [])
            for line in block.get('lines', [])
            for word in line.get('words', [])
        )
        
        # Re-run field extraction on corrected text
        corrected_fields = normalize_text(corrected_full_text)
        
        # Merge with original fields, preserving any that weren't affected
        final_fields = original_fields.copy()
        final_fields.update(corrected_fields)
        
        # Add correction metadata
        final_fields["corrections_applied"] = len(corrections)
        final_fields["last_correction_time"] = max(
            (c.timestamp.isoformat() for c in corrections), 
            default=None
        )
        final_fields["corrected_by_users"] = list(set(c.user_id for c in corrections))
        
        return final_fields
    
    def get_correction_statistics(self, corrections_log_path: Path, doc_id: Optional[str] = None) -> Dict:
        """Get statistics about corrections for analysis and learning."""
        stats = {
            "total_corrections": 0,
            "corrections_by_user": {},
            "corrections_by_field_type": {},
            "common_correction_patterns": {},
            "correction_frequency_by_time": {}
        }
        
        if not corrections_log_path.exists():
            return stats
            
        try:
            with corrections_log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        correction_data = json.loads(line)
                        
                        # Filter by document if specified
                        if doc_id and correction_data.get("document_id") != doc_id:
                            continue
                            
                        stats["total_corrections"] += 1
                        
                        # User statistics
                        user_id = correction_data.get("user_id", "unknown")
                        stats["corrections_by_user"][user_id] = stats["corrections_by_user"].get(user_id, 0) + 1
                        
                        # Track common correction patterns for learning
                        original_text = correction_data.get("original_text", "")
                        corrected_text = correction_data.get("corrected_text", "")
                        
                        if original_text and corrected_text:
                            pattern = f"{original_text} -> {corrected_text}"
                            stats["common_correction_patterns"][pattern] = \
                                stats["common_correction_patterns"].get(pattern, 0) + 1
                                
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping invalid correction entry for stats: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to generate correction statistics: {e}")
            
        return stats

class CorrectionLearner:
    """
    Learns from correction patterns to improve future processing.
    Implements the learning system mentioned in the PRD.
    """
    
    def __init__(self, learning_threshold: int = 3):
        """
        Initialize correction learner.
        
        Args:
            learning_threshold: Number of identical corrections needed to update lexicon
        """
        self.learning_threshold = learning_threshold
        self.correction_lexicon_path = Path("data/correction_lexicon.json")
        self.correction_lexicon_path.parent.mkdir(parents=True, exist_ok=True)
    
    def update_correction_lexicon(self, corrections_log_path: Path):
        """
        Update correction lexicon based on recurring correction patterns.
        Implements the PRD requirement: "Update correction lexicon when same error occurs ≥ 3 times"
        """
        try:
            # Load existing lexicon
            lexicon = self._load_correction_lexicon()
            
            # Get correction statistics
            integrator = CorrectionIntegrator()
            stats = integrator.get_correction_statistics(corrections_log_path)
            
            # Update lexicon with patterns that meet threshold
            updates_made = 0
            for pattern, count in stats["common_correction_patterns"].items():
                if count >= self.learning_threshold:
                    if " -> " in pattern:
                        original, corrected = pattern.split(" -> ", 1)
                        lexicon[original.strip()] = corrected.strip()
                        updates_made += 1
                        
            # Save updated lexicon
            if updates_made > 0:
                self._save_correction_lexicon(lexicon)
                logger.info(f"Updated correction lexicon with {updates_made} new patterns")
            
            return updates_made
            
        except Exception as e:
            logger.error(f"Failed to update correction lexicon: {e}")
            return 0
    
    def _load_correction_lexicon(self) -> Dict[str, str]:
        """Load the correction lexicon from disk."""
        if not self.correction_lexicon_path.exists():
            return {}
            
        try:
            with self.correction_lexicon_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load correction lexicon: {e}")
            return {}
    
    def _save_correction_lexicon(self, lexicon: Dict[str, str]):
        """Save the correction lexicon to disk."""
        try:
            with self.correction_lexicon_path.open("w", encoding="utf-8") as f:
                json.dump(lexicon, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save correction lexicon: {e}")
    
    def get_correction_suggestions(self, text: str) -> List[str]:
        """Get correction suggestions based on learned patterns."""
        lexicon = self._load_correction_lexicon()
        suggestions = []
        
        for original, corrected in lexicon.items():
            if original.lower() in text.lower():
                suggestions.append(f"Consider changing '{original}' to '{corrected}'")
                
        return suggestions

# Global instances
_correction_integrator: Optional[CorrectionIntegrator] = None
_correction_learner: Optional[CorrectionLearner] = None

def get_correction_integrator() -> CorrectionIntegrator:
    """Get or create global CorrectionIntegrator instance."""
    global _correction_integrator
    if _correction_integrator is None:
        _correction_integrator = CorrectionIntegrator()
    return _correction_integrator

def get_correction_learner() -> CorrectionLearner:
    """Get or create global CorrectionLearner instance."""
    global _correction_learner
    if _correction_learner is None:
        _correction_learner = CorrectionLearner()
    return _correction_learner

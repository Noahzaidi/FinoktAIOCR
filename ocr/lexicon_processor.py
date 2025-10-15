import json
import logging
from typing import Dict, List, Tuple
from database.connector import get_db
from database import models
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class LexiconProcessor:
    """Processes OCR output by applying learned lexicon corrections."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.lexicon_cache = {}
    
    def apply_lexicon_corrections(self, ocr_data: Dict, document_type: str = "document") -> Tuple[Dict, List[str]]:
        """
        Apply lexicon corrections to OCR data at word level.
        """
        logger.info(f"🔧 Starting lexicon correction application for document type: {document_type}")
        
        try:
            lexicon = self._load_lexicon(document_type)
            if not lexicon:
                return ocr_data, []
            
            corrected_data = json.loads(json.dumps(ocr_data))
            applied_corrections = []
            
            for page in corrected_data.get("pages", []):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        for word in line.get("words", []):
                            original_value = word.get("value", "").strip()
                            if not original_value:
                                continue
                            
                            corrected_value = self._find_correction(original_value, lexicon)
                            
                            if corrected_value and corrected_value != original_value:
                                word["original_value"] = original_value
                                word["value"] = corrected_value
                                word["auto_corrected"] = True
                                applied_corrections.append(f"'{original_value}' -> '{corrected_value}'")
            
            return corrected_data, applied_corrections
            
        except Exception as e:
            logger.error(f"Error applying lexicon corrections: {e}")
            return ocr_data, []
    
    def _load_lexicon(self, document_type: str) -> Dict[str, str]:
        """Load lexicon data from the database."""
        if document_type in self.lexicon_cache:
            return self.lexicon_cache[document_type]

        lexicon_entries = self.db.query(models.Lexicon).filter(
            (models.Lexicon.document_type == 'global') | (models.Lexicon.document_type == document_type)
        ).all()
        
        lexicon = {entry.misspelled: entry.corrected for entry in lexicon_entries}
        self.lexicon_cache[document_type] = lexicon
        return lexicon

    # ... (keep _find_correction, _normalize_for_comparison, _preserve_case)

# Global processor instance
_lexicon_processor = None

def get_lexicon_processor(db: Session):
    """Get or create global LexiconProcessor instance."""
    global _lexicon_processor
    if _lexicon_processor is None:
        _lexicon_processor = LexiconProcessor(db)
    return _lexicon_processor

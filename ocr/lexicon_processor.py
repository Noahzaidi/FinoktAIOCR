"""
Lexicon-based OCR post-processor
Applies learned corrections to OCR output automatically
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
import logging

logger = logging.getLogger(__name__)

class LexiconProcessor:
    """Processes OCR output by applying learned lexicon corrections."""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.lexicon_cache = {}
        self.cache_timestamp = {}
    
    def apply_lexicon_corrections(self, ocr_data: Dict, document_type: str = "document") -> Tuple[Dict, List[str]]:
        """
        Apply lexicon corrections to OCR data at word level.
        
        Args:
            ocr_data: DocTR OCR output
            document_type: Type of document for type-specific corrections
            
        Returns:
            Tuple of (corrected_ocr_data, list_of_applied_corrections)
        """
        # Always apply corrections - don't depend on config manager for now
        logger.info(f"🔧 Starting lexicon correction application for document type: {document_type}")
        
        # Check if auto-correction is enabled (with fallback)
        auto_correction_enabled = True
        if self.config_manager:
            try:
                auto_correction_enabled = self.config_manager.is_auto_correction_enabled(document_type)
            except Exception as e:
                logger.warning(f"Config manager error, defaulting to enabled: {e}")
        
        if not auto_correction_enabled:
            logger.info("Auto-correction disabled by configuration")
            return ocr_data, []
        
        try:
            # Load lexicon data
            lexicon = self._load_lexicon(document_type)
            logger.info(f"Loaded lexicon for type '{document_type}': {len(lexicon)} patterns")
            if not lexicon:
                logger.info("No lexicon patterns found - returning original OCR data")
                return ocr_data, []
            
            # Deep copy OCR data to avoid modifying original
            corrected_data = json.loads(json.dumps(ocr_data))
            applied_corrections = []
            
            # Process each word in the OCR data
            words_processed = 0
            for page_idx, page in enumerate(corrected_data.get("pages", [])):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        for word in line.get("words", []):
                            words_processed += 1
                            original_value = word.get("value", "").strip()
                            if not original_value:
                                continue
                            
                            # Check if this word should be corrected
                            corrected_value = self._find_correction(original_value, lexicon)
                            
                            # Debug logging for specific patterns
                            if original_value in lexicon:
                                logger.info(f"🎯 Found exact lexicon match: '{original_value}' -> '{corrected_value}'")
                            
                            if corrected_value and corrected_value != original_value:
                                logger.info(f"🔧 Applying auto-correction: '{original_value}' -> '{corrected_value}'")
                                
                                # Store original value
                                word["original_value"] = original_value
                                
                                # Apply correction
                                word["value"] = corrected_value
                                word["auto_corrected"] = True
                                word["corrected_by_lexicon"] = True
                                word["correction_source"] = "lexicon"
                                word["auto_corrected_at"] = __import__("datetime").datetime.utcnow().isoformat()
                                
                                correction_desc = f"'{original_value}' -> '{corrected_value}'"
                                applied_corrections.append(correction_desc)
                                
                                logger.info(f"✅ Applied lexicon correction: {correction_desc}")
            
            logger.info(f"📊 Processed {words_processed} words total")
            
            if applied_corrections:
                logger.info(f"Applied {len(applied_corrections)} lexicon corrections to document")
            
            return corrected_data, applied_corrections
            
        except Exception as e:
            logger.error(f"Error applying lexicon corrections: {e}")
            return ocr_data, []
    
    def _load_lexicon(self, document_type: str) -> Dict[str, str]:
        """Load lexicon data with caching."""
        lexicon_path = Path("data/lexicons/auto_corrections.json")
        type_lexicon_path = Path(f"data/lexicons/{document_type}_corrections.json")
        
        combined_lexicon = {}
        
        # Load global lexicon
        if lexicon_path.exists():
            try:
                # Check if we need to reload (file modified)
                file_mtime = lexicon_path.stat().st_mtime
                if ("global" not in self.cache_timestamp or 
                    self.cache_timestamp["global"] < file_mtime):
                    
                    with lexicon_path.open("r", encoding="utf-8") as f:
                        self.lexicon_cache["global"] = json.load(f)
                    self.cache_timestamp["global"] = file_mtime
                
                combined_lexicon.update(self.lexicon_cache["global"])
                
            except Exception as e:
                logger.warning(f"Failed to load global lexicon: {e}")
        
        # Load document-type specific lexicon
        if type_lexicon_path.exists():
            try:
                file_mtime = type_lexicon_path.stat().st_mtime
                cache_key = f"type_{document_type}"
                
                if (cache_key not in self.cache_timestamp or 
                    self.cache_timestamp[cache_key] < file_mtime):
                    
                    with type_lexicon_path.open("r", encoding="utf-8") as f:
                        self.lexicon_cache[cache_key] = json.load(f)
                    self.cache_timestamp[cache_key] = file_mtime
                
                combined_lexicon.update(self.lexicon_cache[cache_key])
                
            except Exception as e:
                logger.warning(f"Failed to load {document_type} lexicon: {e}")
        
        return combined_lexicon
    
    def _find_correction(self, original_text: str, lexicon: Dict[str, str]) -> str:
        """Find correction for a word in the lexicon with robust matching."""
        # Normalize the input text (strip whitespace)
        normalized_input = original_text.strip()
        
        # Strategy 1: Exact match
        if normalized_input in lexicon:
            logger.debug(f"Exact match found: '{normalized_input}' -> '{lexicon[normalized_input]}'")
            return lexicon[normalized_input]
        
        # Strategy 2: Case-insensitive match
        for original, corrected in lexicon.items():
            if original.lower() == normalized_input.lower():
                logger.debug(f"Case-insensitive match found: '{normalized_input}' -> '{corrected}'")
                return self._preserve_case(normalized_input, corrected)
        
        # Strategy 3: Normalized comparison (remove extra whitespace, normalize special chars)
        normalized_input_clean = self._normalize_for_comparison(normalized_input)
        for original, corrected in lexicon.items():
            original_clean = self._normalize_for_comparison(original)
            if original_clean == normalized_input_clean:
                logger.debug(f"Normalized match found: '{normalized_input}' -> '{corrected}'")
                return corrected
        
        # No match found
        return original_text
    
    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize text for comparison - remove extra spaces, normalize chars."""
        import re
        # Remove extra whitespace and normalize
        normalized = re.sub(r'\s+', ' ', text.strip())
        return normalized
    
    def _preserve_case(self, original: str, corrected: str) -> str:
        """Preserve the case pattern of the original word in the correction."""
        if not original or not corrected:
            return corrected
        
        # If original is all uppercase
        if original.isupper():
            return corrected.upper()
        
        # If original is title case
        if original[0].isupper() and len(original) > 1 and original[1:].islower():
            return corrected[0].upper() + corrected[1:].lower() if len(corrected) > 1 else corrected.upper()
        
        # If original is all lowercase
        if original.islower():
            return corrected.lower()
        
        # Default: return corrected as-is
        return corrected

# Global processor instance
_lexicon_processor = None

def get_lexicon_processor(config_manager=None):
    """Get or create global LexiconProcessor instance."""
    global _lexicon_processor
    if _lexicon_processor is None:
        _lexicon_processor = LexiconProcessor(config_manager)
    return _lexicon_processor

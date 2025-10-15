"""
Anchor-based field extraction system.
Implements spatial reasoning to find values closest to field labels (e.g., find value near "Invoice No").
"""

import re
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AnchorMatch:
    """Represents a field value found near an anchor label."""
    field_name: str
    anchor_text: str
    value_text: str
    confidence: float
    anchor_bbox: List[float]
    value_bbox: List[float]
    distance: float

class AnchorExtractor:
    """
    Extracts field values using spatial anchor-based reasoning.
    Finds values positioned near known field labels in documents.
    """
    
    def __init__(self):
        """Initialize the anchor extractor with field definitions."""
        self.field_anchors = {
            "invoice_number": {
                "patterns": [
                    r"invoice\s*(?:number|no|#)",
                    r"invoice\s*id",
                    r"ref(?:erence)?(?:\s*no)?",
                    r"document\s*(?:number|no)",
                    r"bill\s*(?:number|no)"
                ],
                "value_patterns": [r"[A-Z0-9\-]{3,20}"],
                "search_directions": ["right", "below", "below_right"]
            },
            "date": {
                "patterns": [
                    r"(?:invoice\s*)?date",
                    r"(?:bill\s*)?date",
                    r"issued?\s*(?:on|date)",
                    r"created?\s*(?:on|date)"
                ],
                "value_patterns": [
                    r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}",
                    r"\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}",
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
                ],
                "search_directions": ["right", "below", "below_right"]
            },
            "amount": {
                "patterns": [
                    r"total(?:\s*amount)?",
                    r"amount\s*(?:due|payable)",
                    r"balance\s*(?:due|payable)?",
                    r"grand\s*total",
                    r"net\s*amount",
                    r"subtotal"
                ],
                "value_patterns": [
                    r"[\$\€\£]?\s*\d{1,3}(?:,\d{3})*\.?\d{0,2}",
                    r"\d{1,3}(?:,\d{3})*\.?\d{0,2}\s*[\$\€\£]"
                ],
                "search_directions": ["right", "below", "below_right"]
            },
            "vendor_name": {
                "patterns": [
                    r"from",
                    r"vendor",
                    r"supplier",
                    r"billed?\s*by",
                    r"company"
                ],
                "value_patterns": [r"[A-Za-z][A-Za-z\s&\.,]{2,50}"],
                "search_directions": ["right", "below", "above"]
            },
            "customer_name": {
                "patterns": [
                    r"to",
                    r"customer",
                    r"client",
                    r"billed?\s*to",
                    r"ship\s*to"
                ],
                "value_patterns": [r"[A-Za-z][A-Za-z\s&\.,]{2,50}"],
                "search_directions": ["right", "below"]
            }
        }
        
        # Distance thresholds for different search directions (in relative coordinates)
        self.distance_thresholds = {
            "right": 0.3,      # 30% of document width
            "below": 0.1,      # 10% of document height  
            "below_right": 0.2, # Combined threshold
            "above": 0.1       # 10% of document height
        }
    
    def extract_anchored_fields(self, ocr_data: Dict, image_size: Tuple[int, int] = (1000, 1000)) -> Dict[str, Any]:
        """
        Extract fields using anchor-based spatial reasoning.
        
        Args:
            ocr_data: DocTR OCR output with bounding boxes
            image_size: Document image dimensions for normalization
            
        Returns:
            Dictionary with extracted field values and metadata
        """
        try:
            logger.info("Starting anchor-based field extraction")
            
            # Extract words with positions
            words = self._extract_words_with_positions(ocr_data)
            
            if not words:
                logger.warning("No words found in OCR data")
                return {}
            
            # Find anchors and extract values
            extracted_fields = {}
            anchor_matches = []
            
            for field_name, field_config in self.field_anchors.items():
                matches = self._find_anchored_values(words, field_name, field_config)
                
                if matches:
                    # Use the best match (highest confidence)
                    best_match = max(matches, key=lambda m: m.confidence)
                    extracted_fields[field_name] = best_match.value_text
                    extracted_fields[f"{field_name}_confidence"] = best_match.confidence
                    extracted_fields[f"{field_name}_anchor"] = best_match.anchor_text
                    anchor_matches.append(best_match)
                    
                    logger.info(f"Found {field_name}: '{best_match.value_text}' "
                              f"near anchor '{best_match.anchor_text}' "
                              f"(confidence: {best_match.confidence:.3f})")
            
            # Add metadata
            extracted_fields["anchor_extraction_metadata"] = {
                "total_anchors_found": len(anchor_matches),
                "extraction_method": "spatial_anchoring",
                "field_coverage": len(extracted_fields) / len(self.field_anchors)
            }
            
            logger.info(f"Anchor-based extraction completed. Found {len(anchor_matches)} field values.")
            return extracted_fields
            
        except Exception as e:
            logger.error(f"Anchor-based extraction failed: {e}")
            return {}
    
    def _extract_words_with_positions(self, ocr_data: Dict) -> List[Dict]:
        """Extract words with their text and bounding box positions."""
        words = []
        
        for page_idx, page in enumerate(ocr_data.get("pages", [])):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        text = word.get("value", "").strip()
                        geometry = word.get("geometry", [[0, 0, 0, 0]])[0]
                        
                        if text and len(geometry) == 4:
                            words.append({
                                "text": text,
                                "bbox": geometry,  # [x1, y1, x2, y2] in relative coordinates
                                "page": page_idx,
                                "confidence": word.get("confidence", 0.0)
                            })
        
        return words
    
    def _find_anchored_values(self, words: List[Dict], field_name: str, field_config: Dict) -> List[AnchorMatch]:
        """Find values anchored to field labels."""
        matches = []
        
        # Find anchor words
        anchor_words = self._find_anchor_words(words, field_config["patterns"])
        
        if not anchor_words:
            return matches
            
        # For each anchor, search for values in specified directions
        for anchor_word in anchor_words:
            for direction in field_config["search_directions"]:
                candidate_words = self._find_words_in_direction(
                    words, anchor_word, direction
                )
                
                # Check candidates against value patterns
                for candidate in candidate_words:
                    if self._matches_value_patterns(candidate["text"], field_config["value_patterns"]):
                        distance = self._calculate_distance(anchor_word["bbox"], candidate["bbox"])
                        confidence = self._calculate_anchor_confidence(
                            anchor_word, candidate, distance, direction
                        )
                        
                        match = AnchorMatch(
                            field_name=field_name,
                            anchor_text=anchor_word["text"],
                            value_text=candidate["text"],
                            confidence=confidence,
                            anchor_bbox=anchor_word["bbox"],
                            value_bbox=candidate["bbox"],
                            distance=distance
                        )
                        matches.append(match)
        
        return matches
    
    def _find_anchor_words(self, words: List[Dict], patterns: List[str]) -> List[Dict]:
        """Find words that match anchor patterns."""
        anchor_words = []
        
        for word in words:
            text = word["text"].lower()
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    anchor_words.append(word)
                    break  # Don't double-count the same word
                    
        return anchor_words
    
    def _find_words_in_direction(self, words: List[Dict], anchor_word: Dict, direction: str) -> List[Dict]:
        """Find words in a specific direction from an anchor."""
        anchor_bbox = anchor_word["bbox"]
        anchor_center_x = (anchor_bbox[0] + anchor_bbox[2]) / 2
        anchor_center_y = (anchor_bbox[1] + anchor_bbox[3]) / 2
        
        candidates = []
        threshold = self.distance_thresholds.get(direction, 0.2)
        
        for word in words:
            if word == anchor_word:
                continue
                
            word_bbox = word["bbox"]
            word_center_x = (word_bbox[0] + word_bbox[2]) / 2
            word_center_y = (word_bbox[1] + word_bbox[3]) / 2
            
            # Check if word is in the specified direction within threshold
            if direction == "right":
                if (word_center_x > anchor_center_x and 
                    abs(word_center_y - anchor_center_y) < threshold and
                    word_center_x - anchor_center_x < threshold):
                    candidates.append(word)
                    
            elif direction == "below":
                if (word_center_y > anchor_center_y and
                    abs(word_center_x - anchor_center_x) < threshold and
                    word_center_y - anchor_center_y < threshold):
                    candidates.append(word)
                    
            elif direction == "below_right":
                if (word_center_x > anchor_center_x and word_center_y > anchor_center_y and
                    self._calculate_distance(anchor_bbox, word_bbox) < threshold):
                    candidates.append(word)
                    
            elif direction == "above":
                if (word_center_y < anchor_center_y and
                    abs(word_center_x - anchor_center_x) < threshold and
                    anchor_center_y - word_center_y < threshold):
                    candidates.append(word)
        
        # Sort by distance from anchor
        candidates.sort(key=lambda w: self._calculate_distance(anchor_bbox, w["bbox"]))
        
        return candidates
    
    def _matches_value_patterns(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the value patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _calculate_distance(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate normalized distance between two bounding boxes."""
        center1 = [(bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2]
        center2 = [(bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2]
        
        return np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
    
    def _calculate_anchor_confidence(self, anchor_word: Dict, value_word: Dict, 
                                   distance: float, direction: str) -> float:
        """Calculate confidence score for an anchor-value pair."""
        base_confidence = 0.5
        
        # Distance bonus (closer is better)
        distance_bonus = max(0, 0.3 - distance)
        
        # OCR confidence bonus
        ocr_confidence_bonus = (anchor_word.get("confidence", 0) + value_word.get("confidence", 0)) / 2 * 0.2
        
        # Direction preference bonus (some directions are more reliable)
        direction_bonus = {
            "right": 0.2,
            "below": 0.15,
            "below_right": 0.1,
            "above": 0.05
        }.get(direction, 0)
        
        total_confidence = base_confidence + distance_bonus + ocr_confidence_bonus + direction_bonus
        return min(1.0, total_confidence)

from database.connector import get_db
from database import models
from sqlalchemy.orm import Session

class TemplateMemory:
    """
    Stores and retrieves document-specific field extraction templates from the database.
    """
    
    def __init__(self, db_session: Session):
        """Initialize template memory system with a database session."""
        self.db = db_session
        self.anchor_extractor = AnchorExtractor()
    
    def learn_template_from_corrections(self, doc_id: str, ocr_data: Dict, 
                                      corrections: List[Dict], doc_type: str = "generic"):
        """Learn field positions from user corrections to build/update templates in the database."""
        try:
            template = self.db.query(models.Template).filter(models.Template.document_type == doc_type).first()

            if not template:
                template = models.Template(
                    document_type=doc_type,
                    field_positions={},
                    anchor_patterns={},
                    usage_count=0
                )
                self.db.add(template)
            
            # Update template with correction information
            words = self.anchor_extractor._extract_words_with_positions(ocr_data)
            
            for correction in corrections:
                field_name = correction.get("field_name", "unknown")
                corrected_text = correction.get("corrected_text", "")
                word_bbox = correction.get("corrected_bbox", [])
                
                if field_name != "unknown" and word_bbox:
                    nearby_anchors = self._find_nearby_anchors(words, word_bbox)
                    
                    if nearby_anchors:
                        template.field_positions[field_name] = {
                            "typical_value": corrected_text,
                            "bounding_box": word_bbox,
                            "nearby_anchors": nearby_anchors,
                            "confidence": 0.8
                        }
            
            template.usage_count += 1
            self.db.commit()
            logger.info(f"Updated template for document type: {doc_type}")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to learn template from corrections: {e}")
    
    def _find_nearby_anchors(self, words: List[Dict], target_bbox: List[float], 
                           max_distance: float = 0.2) -> List[str]:
        """Find anchor words near a target bounding box."""
        nearby_anchors = []
        
        for word in words:
            distance = self.anchor_extractor._calculate_distance(word["bbox"], target_bbox)
            if distance < max_distance:
                nearby_anchors.append(word["text"])
                
        return nearby_anchors[:5]  # Limit to top 5 closest anchors

# Global instances
_anchor_extractor: Optional[AnchorExtractor] = None
_template_memory: Optional[TemplateMemory] = None

def get_anchor_extractor() -> AnchorExtractor:
    """Get or create global AnchorExtractor instance."""
    global _anchor_extractor
    if _anchor_extractor is None:
        _anchor_extractor = AnchorExtractor()
    return _anchor_extractor

def get_template_memory() -> TemplateMemory:
    """Get or create global TemplateMemory instance."""
    global _template_memory
    if _template_memory is None:
        _template_memory = TemplateMemory()
    return _template_memory

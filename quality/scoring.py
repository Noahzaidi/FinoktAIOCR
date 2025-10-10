"""
Quality scoring system for OCR and layout analysis results.
Computes confidence scores and routes documents based on quality metrics.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class QualityLevel(Enum):
    """Document quality levels for routing decisions."""
    HIGH = "high"           # > 0.8 - Auto-process
    MEDIUM = "medium"       # 0.5-0.8 - Quick review
    LOW = "low"            # < 0.5 - Full manual review

@dataclass
class QualityMetrics:
    """Container for quality assessment metrics."""
    ocr_confidence: float
    layout_confidence: float
    field_extraction_confidence: float
    overall_quality: float
    quality_level: QualityLevel
    recommendations: List[str]
    
class QualityScorer:
    """
    Computes quality scores for document processing results.
    Combines OCR confidence, layout analysis, and field extraction metrics.
    """
    
    def __init__(self):
        """Initialize the quality scorer with default thresholds."""
        self.high_quality_threshold = 0.8
        self.medium_quality_threshold = 0.5
        
        # Weights for different quality components
        self.weights = {
            "ocr_confidence": 0.4,
            "layout_confidence": 0.3,
            "field_extraction": 0.3
        }
    
    def compute_quality_score(self, 
                            ocr_data: Dict, 
                            layout_data: Optional[Dict] = None,
                            extracted_fields: Optional[Dict] = None) -> QualityMetrics:
        """
        Compute comprehensive quality score for a processed document.
        
        Args:
            ocr_data: DocTR OCR output with confidence scores
            layout_data: LayoutLMv3 analysis results
            extracted_fields: Normalized field extraction results
            
        Returns:
            QualityMetrics with detailed scoring information
        """
        try:
            # Compute individual confidence scores
            ocr_confidence = self._compute_ocr_confidence(ocr_data)
            layout_confidence = self._compute_layout_confidence(layout_data)
            field_confidence = self._compute_field_extraction_confidence(extracted_fields)
            
            # Compute weighted overall score
            overall_quality = (
                ocr_confidence * self.weights["ocr_confidence"] +
                layout_confidence * self.weights["layout_confidence"] +
                field_confidence * self.weights["field_extraction"]
            )
            
            # Determine quality level
            quality_level = self._determine_quality_level(overall_quality)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                ocr_confidence, layout_confidence, field_confidence, quality_level
            )
            
            metrics = QualityMetrics(
                ocr_confidence=ocr_confidence,
                layout_confidence=layout_confidence,
                field_extraction_confidence=field_confidence,
                overall_quality=overall_quality,
                quality_level=quality_level,
                recommendations=recommendations
            )
            
            logger.info(f"Quality assessment completed - Overall: {overall_quality:.3f}, Level: {quality_level.value}")
            return metrics
            
        except Exception as e:
            logger.error(f"Quality scoring failed: {e}")
            return self._fallback_quality_metrics()
    
    def _compute_ocr_confidence(self, ocr_data: Dict) -> float:
        """Compute OCR confidence score from DocTR output."""
        if not ocr_data or "pages" not in ocr_data:
            return 0.0
            
        confidences = []
        
        for page in ocr_data.get("pages", []):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        confidence = word.get("confidence", 0.0)
                        if confidence > 0:  # Only include valid confidences
                            confidences.append(confidence)
        
        if not confidences:
            return 0.0
            
        # Use weighted average (longer words get more weight)
        return float(np.mean(confidences))
    
    def _compute_layout_confidence(self, layout_data: Optional[Dict]) -> float:
        """Compute layout analysis confidence score."""
        if not layout_data:
            return 0.5  # Neutral score when layout analysis not available
            
        # Use layout confidence from LayoutLMv3 if available
        layout_confidence = layout_data.get("layout_confidence", 0.0)
        
        # Bonus for successful field relationship detection
        relationships = layout_data.get("field_relationships", {})
        label_value_pairs = relationships.get("label_value_pairs", [])
        
        if label_value_pairs:
            # Higher confidence when relationships are found
            relationship_bonus = min(0.2, len(label_value_pairs) * 0.05)
            layout_confidence += relationship_bonus
            
        return min(1.0, layout_confidence)
    
    def _compute_field_extraction_confidence(self, extracted_fields: Optional[Dict]) -> float:
        """Compute field extraction confidence based on successful extractions."""
        if not extracted_fields:
            return 0.0
            
        # Key fields to check for
        important_fields = ["invoice_number", "date", "amount", "currency"]
        extracted_count = 0
        total_fields = len(important_fields)
        
        for field in important_fields:
            value = extracted_fields.get(field)
            if value is not None and str(value).strip():
                extracted_count += 1
        
        base_confidence = extracted_count / total_fields
        
        # Bonus for high-quality extractions (valid formats)
        quality_bonus = 0.0
        
        # Check date format quality
        if extracted_fields.get("date"):
            if self._is_valid_date_format(extracted_fields["date"]):
                quality_bonus += 0.1
                
        # Check amount format quality  
        if extracted_fields.get("amount"):
            if isinstance(extracted_fields["amount"], (int, float)) and extracted_fields["amount"] > 0:
                quality_bonus += 0.1
                
        # Check currency format quality
        if extracted_fields.get("currency"):
            if extracted_fields["currency"] in ["USD", "EUR", "GBP", "CAD"]:
                quality_bonus += 0.05
        
        return min(1.0, base_confidence + quality_bonus)
    
    def _is_valid_date_format(self, date_str: str) -> bool:
        """Check if date string appears to be in a valid format."""
        import re
        
        # Common date patterns
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{2}\.\d{2}\.\d{4}', # DD.MM.YYYY
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, str(date_str).strip()):
                return True
        return False
    
    def _determine_quality_level(self, overall_quality: float) -> QualityLevel:
        """Determine quality level based on overall score."""
        if overall_quality >= self.high_quality_threshold:
            return QualityLevel.HIGH
        elif overall_quality >= self.medium_quality_threshold:
            return QualityLevel.MEDIUM
        else:
            return QualityLevel.LOW
    
    def _generate_recommendations(self, 
                                ocr_conf: float, 
                                layout_conf: float, 
                                field_conf: float,
                                quality_level: QualityLevel) -> List[str]:
        """Generate recommendations based on quality metrics."""
        recommendations = []
        
        # OCR-specific recommendations
        if ocr_conf < 0.6:
            recommendations.append("Low OCR confidence - manual text review recommended")
            recommendations.append("Consider document image quality improvements")
            
        # Layout-specific recommendations  
        if layout_conf < 0.5:
            recommendations.append("Layout analysis uncertain - verify field positions")
            recommendations.append("Manual field labeling may be required")
            
        # Field extraction recommendations
        if field_conf < 0.4:
            recommendations.append("Few fields extracted successfully - full manual review needed")
            recommendations.append("Check document format compatibility")
            
        # Overall recommendations based on quality level
        if quality_level == QualityLevel.HIGH:
            recommendations.append("High quality - suitable for automated processing")
        elif quality_level == QualityLevel.MEDIUM:
            recommendations.append("Medium quality - quick review recommended")
        else:
            recommendations.append("Low quality - comprehensive manual review required")
            
        return recommendations
    
    def _fallback_quality_metrics(self) -> QualityMetrics:
        """Return fallback metrics when scoring fails."""
        return QualityMetrics(
            ocr_confidence=0.0,
            layout_confidence=0.0,
            field_extraction_confidence=0.0,
            overall_quality=0.0,
            quality_level=QualityLevel.LOW,
            recommendations=["Quality assessment failed - manual review required"]
        )

class DocumentRouter:
    """
    Routes documents to appropriate review queues based on quality scores.
    """
    
    def __init__(self):
        """Initialize document router."""
        self.scorer = QualityScorer()
    
    def route_document(self, doc_id: str, quality_metrics: QualityMetrics) -> Dict[str, Any]:
        """
        Route document based on quality metrics.
        
        Args:
            doc_id: Document identifier
            quality_metrics: Quality assessment results
            
        Returns:
            Routing decision with queue assignment and priority
        """
        routing_decision = {
            "document_id": doc_id,
            "quality_level": quality_metrics.quality_level.value,
            "overall_quality": quality_metrics.overall_quality,
            "routing_queue": self._determine_queue(quality_metrics.quality_level),
            "priority": self._determine_priority(quality_metrics),
            "estimated_review_time": self._estimate_review_time(quality_metrics),
            "recommendations": quality_metrics.recommendations
        }
        
        logger.info(f"Document {doc_id} routed to {routing_decision['routing_queue']} queue "
                   f"with priority {routing_decision['priority']}")
        
        return routing_decision
    
    def _determine_queue(self, quality_level: QualityLevel) -> str:
        """Determine which review queue to assign the document to."""
        queue_mapping = {
            QualityLevel.HIGH: "auto_process",
            QualityLevel.MEDIUM: "quick_review", 
            QualityLevel.LOW: "full_review"
        }
        return queue_mapping[quality_level]
    
    def _determine_priority(self, quality_metrics: QualityMetrics) -> int:
        """Determine review priority (1=highest, 5=lowest)."""
        if quality_metrics.quality_level == QualityLevel.LOW:
            return 1  # Low quality needs immediate attention
        elif quality_metrics.quality_level == QualityLevel.MEDIUM:
            return 3  # Medium priority
        else:
            return 5  # High quality, lowest priority for manual review
    
    def _estimate_review_time(self, quality_metrics: QualityMetrics) -> int:
        """Estimate review time in minutes."""
        time_estimates = {
            QualityLevel.HIGH: 2,    # Quick verification
            QualityLevel.MEDIUM: 5,  # Moderate review
            QualityLevel.LOW: 15     # Comprehensive review
        }
        return time_estimates[quality_metrics.quality_level]

# Global instances for reuse
_quality_scorer: Optional[QualityScorer] = None
_document_router: Optional[DocumentRouter] = None

def get_quality_scorer() -> QualityScorer:
    """Get or create global QualityScorer instance."""
    global _quality_scorer
    if _quality_scorer is None:
        _quality_scorer = QualityScorer()
    return _quality_scorer

def get_document_router() -> DocumentRouter:
    """Get or create global DocumentRouter instance.""" 
    global _document_router
    if _document_router is None:
        _document_router = DocumentRouter()
    return _document_router

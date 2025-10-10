"""
LayoutLMv3-based layout inference module for document understanding.
Processes OCR output with bounding boxes to identify field relationships and document structure.
"""

import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import torch
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

class LayoutInferenceEngine:
    """
    LayoutLMv3-based document layout understanding engine.
    Identifies field-label relationships and document structure.
    """
    
    def __init__(self, model_name: str = "microsoft/layoutlmv3-base"):
        """Initialize the LayoutLMv3 model and processor."""
        self.model_name = model_name
        self.device = torch.device("cpu")  # CPU-only as per PRD
        
        try:
            logger.info(f"Loading LayoutLMv3 model: {model_name}")
            self.processor = LayoutLMv3Processor.from_pretrained(model_name)
            self.model = LayoutLMv3ForTokenClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            logger.info("LayoutLMv3 model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load LayoutLMv3 model: {e}")
            raise
    
    def process_document(self, image_path: Path, ocr_data: Dict, doc_id: str) -> Dict:
        """
        Process a document using LayoutLMv3 to understand layout and field relationships.
        
        Args:
            image_path: Path to document image
            ocr_data: DocTR OCR output with bounding boxes and text
            doc_id: Document identifier
            
        Returns:
            Dict with layout analysis results including field relationships
        """
        try:
            logger.info(f"Processing layout inference for document: {doc_id}")
            
            # Load the image
            image = Image.open(image_path).convert("RGB")
            
            # Extract words and bounding boxes from OCR data
            words, boxes = self._extract_words_and_boxes(ocr_data, image.size)
            
            if not words:
                logger.warning(f"No words extracted from OCR data for document: {doc_id}")
                return self._empty_layout_result(doc_id)
            
            # Prepare input for LayoutLMv3
            encoding = self.processor(
                image, 
                words, 
                boxes=boxes, 
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )
            
            # Move to device
            encoding = {k: v.to(self.device) for k, v in encoding.items()}
            
            # Run inference
            with torch.no_grad():
                outputs = self.model(**encoding)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
                predicted_labels = torch.argmax(predictions, dim=-1)
            
            # Process results
            layout_result = self._process_predictions(
                words, boxes, predicted_labels[0], predictions[0], doc_id
            )
            
            # Add field relationship analysis
            layout_result["field_relationships"] = self._analyze_field_relationships(
                layout_result["entities"], image.size
            )
            
            # Compute layout confidence score
            layout_result["layout_confidence"] = self._compute_layout_confidence(predictions[0])
            
            logger.info(f"Layout inference completed for document: {doc_id}")
            return layout_result
            
        except Exception as e:
            logger.error(f"Layout inference failed for document {doc_id}: {e}")
            return self._empty_layout_result(doc_id, error=str(e))
    
    def _extract_words_and_boxes(self, ocr_data: Dict, image_size: Tuple[int, int]) -> Tuple[List[str], List[List[int]]]:
        """Extract words and normalized bounding boxes from DocTR OCR output."""
        words = []
        boxes = []
        
        width, height = image_size
        
        for page in ocr_data.get("pages", []):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        text = word.get("value", "").strip()
                        if not text:
                            continue
                            
                        # DocTR uses relative coordinates [0, 1]
                        # Convert to absolute pixel coordinates for LayoutLMv3
                        geometry = word.get("geometry", [[0, 0, 0, 0]])[0]
                        x1, y1, x2, y2 = geometry
                        
                        # Convert to absolute coordinates and ensure proper format
                        abs_x1 = int(x1 * width)
                        abs_y1 = int(y1 * height)
                        abs_x2 = int(x2 * width)
                        abs_y2 = int(y2 * height)
                        
                        # LayoutLMv3 expects [x1, y1, x2, y2] format
                        box = [abs_x1, abs_y1, abs_x2, abs_y2]
                        
                        words.append(text)
                        boxes.append(box)
        
        return words, boxes
    
    def _process_predictions(self, words: List[str], boxes: List[List[int]], 
                           predicted_labels: torch.Tensor, predictions: torch.Tensor, 
                           doc_id: str) -> Dict:
        """Process LayoutLMv3 predictions into structured results."""
        entities = []
        
        # Convert predictions to numpy for easier processing
        predicted_labels_np = predicted_labels.cpu().numpy()
        confidence_scores = torch.max(predictions, dim=-1)[0].cpu().numpy()
        
        # Map label IDs to meaningful names (this would need to be configured based on your model)
        label_map = {
            0: "O",  # Outside
            1: "B-INVOICE_NUMBER",
            2: "I-INVOICE_NUMBER", 
            3: "B-DATE",
            4: "I-DATE",
            5: "B-AMOUNT",
            6: "I-AMOUNT",
            7: "B-CURRENCY",
            8: "I-CURRENCY",
            9: "B-VENDOR",
            10: "I-VENDOR",
            # Add more labels as needed
        }
        
        # Process each word prediction
        for i, (word, box, label_id, confidence) in enumerate(
            zip(words, boxes, predicted_labels_np, confidence_scores)
        ):
            if i >= len(predicted_labels_np):  # Handle potential length mismatch
                break
                
            label = label_map.get(label_id, "O")
            
            if label != "O":  # Only include meaningful predictions
                entities.append({
                    "word": word,
                    "label": label,
                    "confidence": float(confidence),
                    "bounding_box": box,
                    "word_index": i
                })
        
        return {
            "document_id": doc_id,
            "entities": entities,
            "total_words": len(words),
            "total_entities": len(entities)
        }
    
    def _analyze_field_relationships(self, entities: List[Dict], image_size: Tuple[int, int]) -> Dict:
        """Analyze spatial relationships between fields to identify label-value pairs."""
        relationships = {
            "label_value_pairs": [],
            "table_structures": [],
            "field_groups": []
        }
        
        # Group entities by type
        labels = [e for e in entities if e["label"].startswith("B-")]
        values = [e for e in entities if e["label"].startswith("I-") or e["label"].startswith("B-")]
        
        # Find label-value relationships based on proximity
        for label_entity in labels:
            label_box = label_entity["bounding_box"]
            label_center = [(label_box[0] + label_box[2]) / 2, (label_box[1] + label_box[3]) / 2]
            
            # Find closest value of same type
            same_type_values = [
                v for v in values 
                if v["label"].replace("I-", "").replace("B-", "") == 
                   label_entity["label"].replace("B-", "")
                and v != label_entity
            ]
            
            if same_type_values:
                # Find closest value
                closest_value = min(same_type_values, key=lambda v: self._calculate_distance(
                    label_center, [(v["bounding_box"][0] + v["bounding_box"][2]) / 2,
                                  (v["bounding_box"][1] + v["bounding_box"][3]) / 2]
                ))
                
                relationships["label_value_pairs"].append({
                    "label": label_entity,
                    "value": closest_value,
                    "distance": self._calculate_distance(
                        label_center,
                        [(closest_value["bounding_box"][0] + closest_value["bounding_box"][2]) / 2,
                         (closest_value["bounding_box"][1] + closest_value["bounding_box"][3]) / 2]
                    ),
                    "confidence": (label_entity["confidence"] + closest_value["confidence"]) / 2
                })
        
        return relationships
    
    def _calculate_distance(self, point1: List[float], point2: List[float]) -> float:
        """Calculate Euclidean distance between two points."""
        return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)
    
    def _compute_layout_confidence(self, predictions: torch.Tensor) -> float:
        """Compute overall layout confidence score."""
        max_confidences = torch.max(predictions, dim=-1)[0]
        return float(torch.mean(max_confidences).item())
    
    def _empty_layout_result(self, doc_id: str, error: Optional[str] = None) -> Dict:
        """Return empty layout result structure."""
        result = {
            "document_id": doc_id,
            "entities": [],
            "field_relationships": {
                "label_value_pairs": [],
                "table_structures": [],
                "field_groups": []
            },
            "layout_confidence": 0.0,
            "total_words": 0,
            "total_entities": 0
        }
        
        if error:
            result["error"] = error
            
        return result


# Singleton instance for reuse across requests
_layout_engine: Optional[LayoutInferenceEngine] = None

def get_layout_engine() -> LayoutInferenceEngine:
    """Get or create the global LayoutInferenceEngine instance."""
    global _layout_engine
    if _layout_engine is None:
        _layout_engine = LayoutInferenceEngine()
    return _layout_engine

async def process_layout(image_path: Path, ocr_data: Dict, doc_id: str) -> Dict:
    """
    Async wrapper for layout processing.
    
    Args:
        image_path: Path to document image
        ocr_data: DocTR OCR output
        doc_id: Document identifier
        
    Returns:
        Layout analysis results
    """
    engine = get_layout_engine()
    return engine.process_document(image_path, ocr_data, doc_id)

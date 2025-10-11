"""
Document type classification system for FinoktAI OCR.
Classifies documents based on content and layout patterns.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class DocumentType:
    """Represents a document type with its characteristics."""
    name: str
    keywords: List[str]
    patterns: List[str]
    confidence_threshold: float = 0.6
    description: str = ""

class DocumentClassifier:
    """
    Classifies documents based on OCR content and layout patterns.
    Supports learning from user corrections and document-specific rules.
    """
    
    def __init__(self):
        """Initialize the document classifier with predefined types."""
        self.document_types = {
            'invoice': DocumentType(
                name='invoice',
                keywords=['invoice', 'bill', 'amount due', 'total amount', 'due date', 'invoice number'],
                patterns=[
                    r'invoice\s+(?:number|#|no\.?)\s*:?\s*[A-Z0-9-]+',
                    r'amount\s+due\s*:?\s*[\$€£]?\s*\d+',
                    r'due\s+date\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
                ],
                description="Commercial invoices and bills"
            ),
            'receipt': DocumentType(
                name='receipt',
                keywords=['receipt', 'total paid', 'change', 'thank you', 'store', 'cash'],
                patterns=[
                    r'total\s+paid\s*:?\s*[\$€£]?\s*\d+',
                    r'change\s*:?\s*[\$€£]?\s*\d+',
                    r'thank\s+you\s+for\s+your\s+business'
                ],
                description="Purchase receipts and payment confirmations"
            ),
            'identity_document': DocumentType(
                name='identity_document',
                keywords=['passport', 'driver license', 'id card', 'identification', 'date of birth'],
                patterns=[
                    r'passport\s+(?:number|no\.?)\s*:?\s*[A-Z0-9]+',
                    r'driver\s+licen[cs]e',
                    r'date\s+of\s+birth\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
                ],
                description="Identity documents and official IDs"
            ),
            'contract': DocumentType(
                name='contract',
                keywords=['agreement', 'contract', 'terms', 'conditions', 'party', 'signature'],
                patterns=[
                    r'this\s+agreement',
                    r'terms\s+and\s+conditions',
                    r'signature\s*:?\s*_+'
                ],
                description="Legal contracts and agreements"
            ),
            'bank_statement': DocumentType(
                name='bank_statement',
                keywords=['bank statement', 'account', 'balance', 'transaction', 'deposit', 'withdrawal'],
                patterns=[
                    r'account\s+(?:number|no\.?)\s*:?\s*[0-9-]+',
                    r'(?:beginning|ending)\s+balance',
                    r'transaction\s+(?:date|history)'
                ],
                description="Bank statements and financial records"
            )
        }
        
        # Load custom document types if available
        self._load_custom_types()
    
    def classify_document(self, ocr_data: Dict, layout_data: Optional[Dict] = None) -> Tuple[str, float]:
        """
        Classify a document based on its OCR content and optional layout data.
        
        Args:
            ocr_data: OCR results from DocTR
            layout_data: Optional layout analysis results
            
        Returns:
            Tuple of (document_type, confidence_score)
        """
        try:
            # Extract full text from OCR data
            full_text = self._extract_text_from_ocr(ocr_data)
            
            if not full_text.strip():
                return 'unknown', 0.0
            
            # Score each document type
            type_scores = {}
            for type_name, doc_type in self.document_types.items():
                score = self._calculate_type_score(full_text, doc_type, layout_data)
                type_scores[type_name] = score
            
            # Find the best match
            best_type = max(type_scores, key=type_scores.get)
            best_score = type_scores[best_type]
            
            # Apply confidence threshold
            if best_score < self.document_types[best_type].confidence_threshold:
                return 'document', best_score  # Generic document type
            
            logger.info(f"Classified document as '{best_type}' with confidence {best_score:.3f}")
            return best_type, best_score
            
        except Exception as e:
            logger.error(f"Document classification failed: {e}")
            return 'unknown', 0.0
    
    def _extract_text_from_ocr(self, ocr_data: Dict) -> str:
        """Extract full text from OCR data structure."""
        text_parts = []
        
        for page in ocr_data.get('pages', []):
            for block in page.get('blocks', []):
                for line in block.get('lines', []):
                    line_text = ' '.join(word.get('value', '') for word in line.get('words', []))
                    if line_text.strip():
                        text_parts.append(line_text.strip())
        
        return ' '.join(text_parts)
    
    def _calculate_type_score(self, text: str, doc_type: DocumentType, layout_data: Optional[Dict]) -> float:
        """Calculate confidence score for a document type."""
        text_lower = text.lower()
        total_score = 0.0
        max_possible_score = 0.0
        
        # Keyword matching (60% of score)
        keyword_score = 0.0
        keyword_weight = 0.6
        
        for keyword in doc_type.keywords:
            max_possible_score += keyword_weight / len(doc_type.keywords)
            if keyword.lower() in text_lower:
                keyword_score += keyword_weight / len(doc_type.keywords)
                
                # Bonus for multiple occurrences
                occurrences = text_lower.count(keyword.lower())
                if occurrences > 1:
                    keyword_score += min(0.1, (occurrences - 1) * 0.02)
        
        total_score += keyword_score
        
        # Pattern matching (30% of score)
        pattern_score = 0.0
        pattern_weight = 0.3
        
        for pattern in doc_type.patterns:
            max_possible_score += pattern_weight / len(doc_type.patterns)
            if re.search(pattern, text, re.IGNORECASE):
                pattern_score += pattern_weight / len(doc_type.patterns)
        
        total_score += pattern_score
        
        # Layout analysis (10% of score) - placeholder for future enhancement
        layout_score = 0.0
        layout_weight = 0.1
        max_possible_score += layout_weight
        
        if layout_data:
            # This could analyze layout patterns specific to document types
            # For now, just add a small bonus if layout data is available
            layout_score = layout_weight * 0.5
        
        total_score += layout_score
        
        # Normalize score to [0, 1]
        if max_possible_score > 0:
            normalized_score = total_score / max_possible_score
        else:
            normalized_score = 0.0
        
        return min(1.0, normalized_score)
    
    def _load_custom_types(self):
        """Load custom document types from configuration file."""
        try:
            custom_types_path = Path("data/lexicons/custom_document_types.json")
            if custom_types_path.exists():
                with custom_types_path.open("r", encoding="utf-8") as f:
                    custom_data = json.load(f)
                
                for type_name, type_config in custom_data.items():
                    self.document_types[type_name] = DocumentType(
                        name=type_name,
                        keywords=type_config.get('keywords', []),
                        patterns=type_config.get('patterns', []),
                        confidence_threshold=type_config.get('confidence_threshold', 0.6),
                        description=type_config.get('description', f"Custom document type: {type_name}")
                    )
                
                logger.info(f"Loaded {len(custom_data)} custom document types")
                
        except Exception as e:
            logger.warning(f"Failed to load custom document types: {e}")
    
    def add_custom_type(self, type_name: str, keywords: List[str], patterns: List[str], 
                       confidence_threshold: float = 0.6, description: str = ""):
        """Add a new custom document type."""
        self.document_types[type_name] = DocumentType(
            name=type_name,
            keywords=keywords,
            patterns=patterns,
            confidence_threshold=confidence_threshold,
            description=description or f"Custom document type: {type_name}"
        )
        
        # Save to persistent storage
        self._save_custom_types()
        logger.info(f"Added custom document type: {type_name}")
    
    def _save_custom_types(self):
        """Save custom document types to configuration file."""
        try:
            custom_types_path = Path("data/lexicons/custom_document_types.json")
            custom_types_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Filter out built-in types
            builtin_types = {'invoice', 'receipt', 'identity_document', 'contract', 'bank_statement'}
            custom_types = {
                name: {
                    'keywords': doc_type.keywords,
                    'patterns': doc_type.patterns,
                    'confidence_threshold': doc_type.confidence_threshold,
                    'description': doc_type.description
                }
                for name, doc_type in self.document_types.items()
                if name not in builtin_types
            }
            
            with custom_types_path.open("w", encoding="utf-8") as f:
                json.dump(custom_types, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save custom document types: {e}")
    
    def get_type_info(self, type_name: str) -> Optional[DocumentType]:
        """Get information about a specific document type."""
        return self.document_types.get(type_name)
    
    def list_types(self) -> Dict[str, str]:
        """List all available document types with descriptions."""
        return {name: doc_type.description for name, doc_type in self.document_types.items()}

# Global classifier instance
_document_classifier: Optional[DocumentClassifier] = None

def get_document_classifier() -> DocumentClassifier:
    """Get or create global DocumentClassifier instance."""
    global _document_classifier
    if _document_classifier is None:
        _document_classifier = DocumentClassifier()
    return _document_classifier

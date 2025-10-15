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

from database.connector import get_db
from database import models
from sqlalchemy.orm import Session

class DocumentClassifier:
    """
    Classifies documents based on OCR content and layout patterns.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the document classifier with a database session."""
        self.db = db_session
        self.document_types = self._load_document_types()
    
    def _load_document_types(self) -> Dict[str, DocumentType]:
        """Load all document types from the database."""
        all_types = self.db.query(models.DocumentType).all()
        return {t.name: DocumentType(
            name=t.name,
            keywords=t.keywords,
            patterns=t.patterns,
            confidence_threshold=t.confidence_threshold,
            description=t.description
        ) for t in all_types}

    def add_custom_type(self, type_name: str, keywords: List[str], patterns: List[str], 
                       confidence_threshold: float = 0.6, description: str = ""):
        """Add a new custom document type to the database."""
        new_type = models.DocumentType(
            name=type_name,
            keywords=keywords,
            patterns=patterns,
            confidence_threshold=confidence_threshold,
            description=description
        )
        self.db.add(new_type)
        self.db.commit()
        self.document_types = self._load_document_types() # Refresh cache
        logger.info(f"Added custom document type: {type_name}")
    
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

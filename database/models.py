import uuid
from sqlalchemy import (create_engine, Column, String, Integer, Float, DateTime, 
                        ForeignKey, JSON, Boolean, LargeBinary)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .connector import Base

class Document(Base):
    __tablename__ = 'documents'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    content_type = Column(String)
    storage_path = Column(String)
    status = Column(String, default='uploaded')
    document_type = Column(String, default='unknown')  # Type of document (invoice, receipt, etc.)
    quality_score = Column(Float)
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    processing_error = Column(String)
    
    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")
    extracted_fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = 'pages'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    image_path = Column(String, nullable=False)
    dimensions = Column(JSON) # {'width': w, 'height': h}
    
    document = relationship("Document", back_populates="pages")
    words = relationship("Word", back_populates="page", cascade="all, delete-orphan")

class Word(Base):
    __tablename__ = 'words'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id = Column(UUID(as_uuid=True), ForeignKey('pages.id', ondelete="CASCADE"), nullable=False)
    text = Column(String, nullable=False)
    confidence = Column(Float)
    geometry = Column(JSON, nullable=False) # bbox array
    
    page = relationship("Page", back_populates="words")
    applied_corrections = relationship("AppliedCorrection", back_populates="word", cascade="all, delete-orphan")

class ExtractedField(Base):
    __tablename__ = 'extracted_fields'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    field_name = Column(String, nullable=False)
    field_value = Column(String)
    confidence = Column(Float)
    
    document = relationship("Document", back_populates="extracted_fields")

class AppliedCorrection(Base):
    __tablename__ = 'applied_corrections'
    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(UUID(as_uuid=True), ForeignKey('words.id', ondelete="CASCADE"), nullable=False)
    original_text = Column(String)
    corrected_text = Column(String, nullable=False)
    correction_source = Column(String, default='manual')
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    word = relationship("Word", back_populates="applied_corrections")

class Correction(Base):
    __tablename__ = 'corrections'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=True)  # Matches existing schema
    word_id = Column(UUID(as_uuid=True), nullable=True)  # Matches existing schema
    original_text = Column(String, nullable=False)
    corrected_text = Column(String, nullable=False)
    context = Column(String)  # Existing column in database
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    # Note: page, corrected_bbox, user_id, correction_type columns will be added
    # by running SQL_FIX_CORRECTIONS_TABLE.sql as database admin

class Lexicon(Base):
    __tablename__ = 'lexicons'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    misspelled = Column(String, nullable=False, unique=True, index=True)
    corrected = Column(String, nullable=False)
    document_type = Column(String, default='global', nullable=False) # 'global' or a specific doc type
    frequency = Column(Integer, default=1)

class TrainingSample(Base):
    __tablename__ = 'training_samples'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word_id = Column(UUID(as_uuid=True), ForeignKey('words.id'), nullable=True)
    image_path = Column(String, nullable=False) # Path to the word image snippet
    label = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DeployedModel(Base):
    __tablename__ = 'deployed_models'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String, nullable=False, unique=True)
    deployment_date = Column(DateTime(timezone=True), server_default=func.now())
    accuracy = Column(Float)
    model_data = Column(LargeBinary) # To store the model file itself
    is_active = Column(Boolean, default=True)

class TrainingReport(Base):
    __tablename__ = 'training_reports'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_id = Column(String, unique=True)
    base_model = Column(String)
    new_model_name = Column(String, ForeignKey('deployed_models.model_name'))
    metrics = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Template(Base):
    __tablename__ = 'templates'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_type = Column(String, nullable=False, unique=True, index=True)
    field_positions = Column(JSON)
    anchor_patterns = Column(JSON)
    confidence_threshold = Column(Float, default=0.7)
    usage_count = Column(Integer, default=0)

class DocumentType(Base):
    __tablename__ = 'document_types'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True, index=True)
    keywords = Column(JSON)
    patterns = Column(JSON)
    confidence_threshold = Column(Float, default=0.6)
    description = Column(String)
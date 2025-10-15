-- This script initializes the database schema for the FinoktAI OCR System.
-- It creates all necessary tables, relationships, and extensions.

-- Enable UUID generation functions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Documents Table: Stores metadata for each uploaded document.
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR NOT NULL,
    content_type VARCHAR,
    upload_date TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR DEFAULT 'uploaded',
    quality_score FLOAT
);

-- 2. Pages Table: Stores information for each page of a document.
CREATE TABLE pages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INT NOT NULL,
    image_path VARCHAR NOT NULL, -- Path to the page image (e.g., _page_0.png)
    dimensions JSON -- {'width': w, 'height': h}
);

-- 3. Words Table: For every word detected by OCR. Replaces _raw.json.
CREATE TABLE words (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    text VARCHAR NOT NULL,
    confidence FLOAT,
    geometry JSON NOT NULL -- [[x1, y1], [x2, y2]]
);

-- 4. Extracted Fields Table: For the final key-value data. Replaces _extracted.json.
CREATE TABLE extracted_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name VARCHAR NOT NULL,
    field_value VARCHAR,
    confidence FLOAT
);

-- 5. Corrections Table: Log of manual corrections.
CREATE TABLE corrections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    word_id UUID REFERENCES words(id) ON DELETE SET NULL,
    original_text VARCHAR NOT NULL,
    corrected_text VARCHAR NOT NULL,
    context VARCHAR,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Lexicons Table: The lexicon. Replaces auto_corrections.json and document-specific lexicons.
CREATE TABLE lexicons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    misspelled VARCHAR NOT NULL UNIQUE,
    corrected VARCHAR NOT NULL,
    document_type VARCHAR NOT NULL DEFAULT 'global', -- 'global' or a specific doc type
    frequency INT DEFAULT 1
);
CREATE INDEX idx_lexicons_misspelled ON lexicons(misspelled);

-- 7. Training Samples Table: For model fine-tuning.
CREATE TABLE training_samples (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    word_id UUID REFERENCES words(id) ON DELETE SET NULL,
    image_path VARCHAR NOT NULL, -- Path to the word image snippet
    label VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Deployed Models Table: Tracks deployed models.
CREATE TABLE deployed_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name VARCHAR NOT NULL UNIQUE,
    deployment_date TIMESTAMPTZ DEFAULT NOW(),
    accuracy FLOAT,
    model_data BYTEA, -- Store the model file directly in the DB
    is_active BOOLEAN DEFAULT TRUE
);

-- 9. Training Reports Table: Logs results from training sessions.
CREATE TABLE training_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    training_id VARCHAR UNIQUE,
    base_model VARCHAR,
    new_model_name VARCHAR REFERENCES deployed_models(model_name),
    metrics JSON,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 10. Templates Table: For storing document-specific field extraction templates.
CREATE TABLE templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_type VARCHAR NOT NULL UNIQUE,
    field_positions JSON,
    anchor_patterns JSON,
    confidence_threshold FLOAT DEFAULT 0.7,
    usage_count INT DEFAULT 0
);
CREATE INDEX idx_templates_document_type ON templates(document_type);

-- 11. Document Types Table: For storing document type definitions for classification.
CREATE TABLE document_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL UNIQUE,
    keywords JSON,
    patterns JSON,
    confidence_threshold FLOAT DEFAULT 0.6,
    description VARCHAR
);
CREATE INDEX idx_document_types_name ON document_types(name);

-- Grant privileges to the app user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO finoktai_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO finoktai_app;
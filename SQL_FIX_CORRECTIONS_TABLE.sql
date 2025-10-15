                        -- Run this SQL as database admin/superuser to update the corrections table schema
-- This fixes the mismatch between the model and the existing database table

-- Connect to your database as a superuser and run these commands:

-- Add missing columns to corrections table
ALTER TABLE corrections ADD COLUMN IF NOT EXISTS page INTEGER;
ALTER TABLE corrections ADD COLUMN IF NOT EXISTS corrected_bbox JSON;
ALTER TABLE corrections ADD COLUMN IF NOT EXISTS user_id VARCHAR DEFAULT 'system';
ALTER TABLE corrections ADD COLUMN IF NOT EXISTS correction_type VARCHAR DEFAULT 'text_edit';

-- Modify columns to VARCHAR for flexibility (optional but recommended)
-- Note: This requires no data in the table or careful data migration
-- ALTER TABLE corrections ALTER COLUMN document_id TYPE VARCHAR USING document_id::VARCHAR;
-- ALTER TABLE corrections ALTER COLUMN word_id TYPE VARCHAR USING word_id::VARCHAR;

-- Add index if not exists
CREATE INDEX IF NOT EXISTS ix_corrections_document_id ON corrections(document_id);

-- Grant permissions to application user
GRANT ALL PRIVILEGES ON TABLE corrections TO finoktai_app;

-- Verify the schema
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'corrections' 
ORDER BY ordinal_position;


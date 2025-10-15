import argparse
import json
import logging
from pathlib import Path
import uuid
from sqlalchemy.orm import sessionmaker
from database.connector import engine
from database import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Migration:
    def __init__(self, dry_run=False, resume=False):
        self.dry_run = dry_run
        self.resume = resume
        Session = sessionmaker(bind=engine)
        self.session = Session()

    def run(self):
        logger.info("Starting JSON to database migration...")
        self.migrate_lexicons()
        self.migrate_documents()
        self.migrate_corrections()
        logger.info("Migration complete.")

    def migrate_documents(self):
        logger.info("Migrating documents...")
        outputs_dir = Path("data/outputs")
        doc_ids = {p.stem.split('_')[0] for p in outputs_dir.glob("*.json")}

        for doc_id in doc_ids:
            self.migrate_document(doc_id, outputs_dir)

    def migrate_document(self, doc_id, outputs_dir):
        # Validate and convert doc_id to UUID
        try:
            doc_uuid = uuid.UUID(doc_id)
        except ValueError:
            logger.warning(f"Invalid UUID format '{doc_id}', generating new UUID for this document.")
            doc_uuid = uuid.uuid4()
        
        # Check if document already exists (for resume functionality)
        if self.resume:
            existing_doc = self.session.query(models.Document).get(doc_uuid)
            if existing_doc:
                logger.info(f"Skipping document {doc_uuid} (already migrated).")
                return

        logger.info(f"Migrating document {doc_id} as UUID {doc_uuid}...")

        raw_ocr_path = outputs_dir / f"{doc_id}_raw.json"
        if not raw_ocr_path.exists():
            logger.warning(f"_raw.json for {doc_id} not found, skipping document.")
            return

        with open(raw_ocr_path, 'r') as f:
            raw_data = json.load(f)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would migrate document {doc_id} as {doc_uuid}.")
            return

        # Check one more time before insert (prevent race conditions)
        try:
            existing_doc = self.session.query(models.Document).get(doc_uuid)
            if existing_doc:
                logger.warning(f"Document {doc_uuid} already exists, skipping.")
                return
        except Exception as e:
            logger.warning(f"Error checking for existing document: {e}")
        
        # Create Document with validated UUID
        doc = models.Document(
            id=doc_uuid,
            filename=f"{doc_id}.pdf", # Placeholder
            status='migrated'
        )
        self.session.add(doc)

        # Create Pages and Words
        for page_data in raw_data.get('pages', []):
            page = models.Page(
                document_id=doc.id,
                page_number=page_data.get('page_num', 0) - 1,
                image_path=f"/data/outputs/{doc_id}_page_{page_data.get('page_num', 1) - 1}.png",
                dimensions={}
            )
            self.session.add(page)
            self.session.commit() # Commit page to get id

            for word_data in page_data.get('words', []):
                word = models.Word(
                    page_id=page.id,
                    text=word_data.get('text'),
                    confidence=word_data.get('confidence'),
                    geometry=word_data.get('bbox')
                )
                self.session.add(word)

        # Migrate Extracted Fields
        extracted_path = outputs_dir / f"{doc_id}_extracted.json"
        if extracted_path.exists():
            with open(extracted_path, 'r') as f:
                extracted_data = json.load(f)
            for field_name, field_value in extracted_data.items():
                if isinstance(field_value, (dict, list)):
                    continue
                field = models.ExtractedField(
                    document_id=doc.id,
                    field_name=field_name,
                    field_value=str(field_value)
                )
                self.session.add(field)

        # Migrate Quality Score
        quality_path = outputs_dir / f"{doc_id}_quality.json"
        if quality_path.exists():
            with open(quality_path, 'r') as f:
                quality_data = json.load(f)
            doc.quality_score = quality_data.get('quality_metrics', {}).get('overall_quality')

        self.session.commit()

    def migrate_lexicons(self):
        logger.info("Migrating lexicons...")
        lexicon_path = Path("data/lexicons/auto_corrections.json")
        frequency_path = Path("data/lexicons/correction_frequency.json")

        if not lexicon_path.exists():
            logger.warning("auto_corrections.json not found, skipping lexicon migration.")
            return

        with open(lexicon_path, 'r') as f:
            lexicon_data = json.load(f)

        frequency_data = {}
        if frequency_path.exists():
            with open(frequency_path, 'r') as f:
                frequency_data = json.load(f)

        for original_term, corrected_term in lexicon_data.items():
            frequency = frequency_data.get(original_term, {}).get(corrected_term, 1)
            
            if self.dry_run:
                logger.info(f"[DRY RUN] Would migrate lexicon: '{original_term}' -> '{corrected_term}' (frequency: {frequency})")
                continue

            lexicon_entry = self.session.query(models.Lexicon).filter_by(misspelled=original_term).first()
            if lexicon_entry:
                lexicon_entry.corrected = corrected_term
                lexicon_entry.frequency = frequency
            else:
                lexicon_entry = models.Lexicon(
                    misspelled=original_term,
                    corrected=corrected_term,
                    frequency=frequency
                )
                self.session.add(lexicon_entry)
        
        if not self.dry_run:
            self.session.commit()

    def migrate_corrections(self):
        logger.info("Migrating corrections...")
        corrections_dir = Path("data/logs/corrections")
        if not corrections_dir.exists():
            logger.warning("Corrections directory not found, skipping.")
            return

        for log_file in corrections_dir.glob("*.json"):
            doc_id = log_file.stem
            with open(log_file, 'r') as f:
                try:
                    corrections_data = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"Could not decode JSON from {log_file}, skipping.")
                    continue

            for correction in corrections_data.get("corrections", []):
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would migrate correction for doc {doc_id}: '{correction.get('original_text')}' -> '{correction.get('corrected_text')}'")
                    continue

                # Validate doc_id as UUID
                try:
                    doc_uuid = uuid.UUID(doc_id)
                except ValueError:
                    logger.warning(f"Invalid UUID format for doc_id '{doc_id}' in correction log {log_file}, skipping correction.")
                    continue

                # Find the word to associate with the correction
                word = self.session.query(models.Word).join(models.Page).filter(
                    models.Page.document_id == doc_uuid,
                    models.Page.page_number == correction.get('page'),
                    models.Word.text == correction.get('original_text')
                ).first()

                if word:
                    applied_correction = models.AppliedCorrection(
                        word_id=word.id,
                        original_text=correction.get('original_text'),
                        corrected_text=correction.get('corrected_text'),
                        correction_source='manual_log'
                    )
                    self.session.add(applied_correction)
                else:
                    logger.warning(f"Could not find matching word for correction in doc {doc_id}: {correction}")
        
        if not self.dry_run:
            self.session.commit()

def main():
    parser = argparse.ArgumentParser(description="Migrate JSON data to the PostgreSQL database.")
    parser.add_argument("command", choices=["migrate-json-to-db"], help="The command to execute.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without committing changes.")
    parser.add_argument("--resume", action="store_true", help="Resume a previously interrupted migration.")
    args = parser.parse_args()

    if args.command == "migrate-json-to-db":
        migration = Migration(dry_run=args.dry_run, resume=args.resume)
        migration.run()

if __name__ == "__main__":
    main()

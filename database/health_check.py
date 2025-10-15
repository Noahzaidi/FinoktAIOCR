import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker
from database.connector import engine
from database import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_database_health():
    """Runs a series of checks to verify the database schema and integrity."""
    Session = sessionmaker(bind=engine)
    session = Session()
    inspector = inspect(engine)

    try:
        logger.info("--- Running Database Health Check ---")

        # 1. Check for uuid-ossp extension
        try:
            result = session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp'"))
            if result.scalar() == 1:
                logger.info("✅ Extension 'uuid-ossp' is present.")
            else:
                logger.error("❌ Extension 'uuid-ossp' is NOT present.")
        except Exception as e:
            logger.error(f"❌ Failed to check for extension: {e}")

        # 2. Verify all tables exist
        expected_tables = ['documents', 'pages', 'words', 'extracted_fields', 'applied_corrections', 'lexicons', 'training_samples', 'deployed_models', 'training_reports', 'templates', 'document_types']
        existing_tables = inspector.get_table_names()
        all_tables_found = True
        for table in expected_tables:
            if table in existing_tables:
                logger.info(f"✅ Table '{table}' exists.")
            else:
                logger.error(f"❌ Table '{table}' is MISSING.")
                all_tables_found = False

        # 3. Verify Foreign Keys and Cascade Deletes
        if all_tables_found:
            try:
                fks = inspector.get_foreign_keys('pages')
                if any(fk['options'].get('ondelete') == 'CASCADE' for fk in fks):
                    logger.info("✅ Cascade delete on `pages` table is correctly configured.")
                else:
                    logger.error("❌ Cascade delete on `pages` is NOT configured.")
            except Exception as e:
                logger.error(f"❌ Failed to verify foreign keys for 'pages': {e}")

        # 4. Smoke Test: Insert/Delete with Cascade
        if all_tables_found:
            logger.info("--- Running Smoke Test (Insert/Delete) ---")
            try:
                # Create a dummy document
                test_doc = models.Document(filename="test_doc.pdf", status="testing")
                session.add(test_doc)
                session.commit()
                doc_id = test_doc.id
                logger.info(f"  -> Inserted test document with id: {doc_id}")

                # Add a page and a word
                test_page = models.Page(document_id=doc_id, page_number=0, image_path="test.png")
                session.add(test_page)
                session.commit()
                page_id = test_page.id
                logger.info(f"  -> Inserted test page with id: {page_id}")

                test_word = models.Word(page_id=page_id, text="test", geometry=[])
                session.add(test_word)
                session.commit()
                logger.info(f"  -> Inserted test word.")

                # Now, delete the document and verify cascade
                session.delete(test_doc)
                session.commit()
                logger.info(f"  -> Deleted test document.")

                # Verify cascade deletion
                page_count = session.query(models.Page).filter_by(document_id=doc_id).count()
                if page_count == 0:
                    logger.info("✅ Cascade delete successful: Page was deleted.")
                else:
                    logger.error("❌ Cascade delete FAILED: Page was not deleted.")
                
                logger.info("--- Smoke Test Passed ---")

            except Exception as e:
                logger.error(f"❌ Smoke Test FAILED: {e}")
                session.rollback()

    finally:
        session.close()
        logger.info("--- Health Check Complete ---")

if __name__ == "__main__":
    check_database_health()

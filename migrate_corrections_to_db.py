#!/usr/bin/env python
"""
Migrate corrections from JSON files to database.
This script reads all correction JSON files from data/logs/corrections/ and imports them into the database.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from database.connector import get_db
from database import models
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_corrections():
    """Migrate all correction JSON files to database."""
    corrections_dir = Path("data/logs/corrections")
    
    if not corrections_dir.exists():
        logger.error(f"Corrections directory not found: {corrections_dir}")
        return 0
    
    # Get all JSON files
    json_files = list(corrections_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} correction files to migrate")
    
    if not json_files:
        logger.warning("No correction files found to migrate")
        return 0
    
    db = next(get_db())
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        for json_file in json_files:
            try:
                logger.info(f"Processing: {json_file.name}")
                
                with open(json_file, 'r', encoding='utf-8') as f:
                    correction_data = json.load(f)
                
                # Extract data from JSON
                # Typical structure might be:
                # {
                #   "document_id": "...",
                #   "corrections": [...]
                # }
                # Or it might be a single correction per file
                
                if isinstance(correction_data, list):
                    # List of corrections
                    corrections_list = correction_data
                elif isinstance(correction_data, dict):
                    # Could be a single correction or have a corrections key
                    if 'corrections' in correction_data:
                        corrections_list = correction_data['corrections']
                    else:
                        # Single correction
                        corrections_list = [correction_data]
                else:
                    logger.warning(f"Unknown format in {json_file.name}, skipping")
                    skipped_count += 1
                    continue
                
                # Process each correction
                for correction in corrections_list:
                    try:
                        # Extract fields from JSON
                        doc_id = correction.get('document_id')
                        original_text = correction.get('original_text')
                        corrected_text = correction.get('corrected_text')
                        word_id = correction.get('word_id')  # This is a string like 'p1_w41', not UUID
                        timestamp_str = correction.get('timestamp')
                        page = correction.get('page')
                        corrected_bbox = correction.get('corrected_bbox')
                        user_id = correction.get('user_id', 'migrated')
                        
                        if not original_text or not corrected_text:
                            logger.warning(f"Missing required fields in correction, skipping")
                            skipped_count += 1
                            continue
                        
                        # Parse timestamp
                        timestamp = None
                        if timestamp_str:
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            except:
                                timestamp = datetime.now()
                        else:
                            timestamp = datetime.now()
                        
                        # Convert document_id to UUID
                        from uuid import UUID
                        try:
                            doc_uuid = UUID(doc_id) if doc_id else None
                        except:
                            doc_uuid = None
                            logger.warning(f"Invalid document UUID: {doc_id}")
                        
                        # Note: word_id in JSON is a string like 'p1_w41', not a UUID
                        # We'll store it in context for now since the DB schema might not have all fields
                        context_data = {
                            'word_id': word_id,
                            'page': page,
                            'user_id': user_id
                        }
                        if corrected_bbox:
                            context_data['corrected_bbox'] = corrected_bbox
                        
                        context = json.dumps(context_data)
                        
                        # Check if correction already exists
                        existing = db.query(models.Correction).filter(
                            models.Correction.document_id == doc_uuid,
                            models.Correction.original_text == original_text,
                            models.Correction.corrected_text == corrected_text
                        ).first()
                        
                        if existing:
                            logger.debug(f"Correction already exists, skipping")
                            skipped_count += 1
                            continue
                        
                        # Create new correction record
                        # Note: Using only fields that exist in current DB schema
                        new_correction = models.Correction(
                            document_id=doc_uuid,
                            word_id=None,  # Current schema expects UUID, but JSON has string
                            original_text=original_text,
                            corrected_text=corrected_text,
                            context=context,  # Store extra data here
                            timestamp=timestamp
                        )
                        
                        db.add(new_correction)
                        migrated_count += 1
                        logger.info(f"  Migrated: '{original_text[:30]}...' -> '{corrected_text[:30]}...'")
                        
                    except Exception as e:
                        logger.error(f"  Error processing correction: {e}")
                        error_count += 1
                        continue
                
            except Exception as e:
                logger.error(f"Error processing file {json_file.name}: {e}")
                error_count += 1
                continue
        
        # Commit all changes
        db.commit()
        logger.info(f"\n=== Migration Summary ===")
        logger.info(f"Total files processed: {len(json_files)}")
        logger.info(f"Corrections migrated: {migrated_count}")
        logger.info(f"Corrections skipped: {skipped_count}")
        logger.info(f"Errors: {error_count}")
        
        return migrated_count
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        db.close()

def preview_corrections():
    """Preview what would be migrated without actually migrating."""
    corrections_dir = Path("data/logs/corrections")
    
    if not corrections_dir.exists():
        print(f"Corrections directory not found: {corrections_dir}")
        return
    
    json_files = list(corrections_dir.glob("*.json"))
    print(f"\n=== Preview: {len(json_files)} correction files found ===\n")
    
    for json_file in json_files[:5]:  # Show first 5 as preview
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"File: {json_file.name}")
            print(f"  Content preview: {str(data)[:200]}...")
            print()
        except Exception as e:
            print(f"File: {json_file.name} - Error: {e}")
            print()
    
    if len(json_files) > 5:
        print(f"... and {len(json_files) - 5} more files")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        print("Running in PREVIEW mode (no changes will be made)")
        preview_corrections()
    else:
        print("Starting corrections migration...")
        print("(Run with --preview to see what would be migrated)")
        print()
        
        response = input("Proceed with migration? (yes/no): ").lower()
        if response in ['yes', 'y']:
            count = migrate_corrections()
            if count > 0:
                print(f"\n✓ Successfully migrated {count} corrections!")
            else:
                print("\n⚠ No corrections were migrated")
        else:
            print("Migration cancelled")


"""
Training Service
High-level interface for OCR model retraining.
"""

import torch
from pathlib import Path
import logging
import json
from datetime import datetime
from typing import Dict, Optional

from training.doctr_finetuning import (
    OCRCorrectionDataset,
    SimpleRecognitionModel,
    OCRTrainer
)

logger = logging.getLogger(__name__)


from database.connector import get_db
from database import models
from sqlalchemy.orm import Session

class TrainingService:
    """Service for managing OCR model training."""
    
    def __init__(
        self,
        db_session: Session,
        models_dir: Path = Path("models/ocr_weights"),
        device: Optional[str] = None
    ):
        self.db = db_session
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        if device is None:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            self.device = device
    
    def count_samples(self) -> int:
        """Count available training samples from the database."""
        return self.db.query(models.TrainingSample).count()
    
    def prepare_datasets(self, val_ratio: float = 0.2):
        """Prepare train and validation datasets from the database."""
        logger.info("Loading training samples from database...")
        
        all_samples = self.db.query(models.TrainingSample).all()
        if not all_samples:
            raise ValueError("No valid training samples found in the database")

        # This is a placeholder for creating a PyTorch dataset from DB objects
        # You would need a custom Dataset class that takes these objects.
        full_dataset = OCRCorrectionDataset(all_samples) # This needs to be adapted
        
        train_size = int(len(full_dataset) * (1 - val_ratio))
        val_size = len(full_dataset) - train_size
        
        train_dataset, val_dataset = torch.utils.data.random_split(
            full_dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(42)
        )
        
        return train_dataset, val_dataset, full_dataset.vocab

    def train_model(
        self,
        num_epochs: int = 20,
        batch_size: int = 16,
        learning_rate: float = 0.001,
        val_ratio: float = 0.2,
    ) -> Dict:
        """Train OCR model on collected samples."""
        # ... (training logic remains the same) ...

        # Save training report to the database
        report_entry = models.TrainingReport(
            training_id=f"training_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            base_model="doctr", # Or another base model identifier
            new_model_name=str(final_model_path),
            metrics=serializable_report, # The JSON-serializable report
        )
        self.db.add(report_entry)
        self.db.commit()

        logger.info(f"Training report saved to database.")
        return report


    
    def load_trained_model(self, checkpoint_path: Optional[Path] = None):
        """
        Load a trained model for inference.
        
        Args:
            checkpoint_path: Path to checkpoint, or None for latest
        """
        if checkpoint_path is None:
            checkpoint_path = self.models_dir / "best_model.pth"
            if not checkpoint_path.exists():
                checkpoint_path = self.models_dir / "latest_model.pth"
        
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"No trained model found at {checkpoint_path}")
        
        logger.info(f"Loading model from {checkpoint_path}")
        
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        # Recreate model
        vocab = checkpoint['vocab']
        model = SimpleRecognitionModel(
            vocab_size=len(vocab),
            hidden_size=256
        )
        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(self.device)
        model.eval()
        
        logger.info(f"✅ Model loaded successfully")
        logger.info(f"Vocabulary size: {len(vocab)}")
        logger.info(f"Training epoch: {checkpoint.get('epoch', 'unknown')}")
        logger.info(f"Validation accuracy: {checkpoint.get('accuracy', 'unknown')}")
        
        return model, vocab


# Convenience function for training
def train_ocr_model(
    samples_dir: Path = Path("data/training_data/ocr_samples"),
    models_dir: Path = Path("models/ocr_weights"),
    num_epochs: int = 20,
    batch_size: int = 16,
    learning_rate: float = 0.001
) -> Dict:
    """
    Convenience function to train OCR model.
    
    Args:
        samples_dir: Directory containing training samples
        models_dir: Directory to save trained models
        num_epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
    
    Returns:
        Training report dictionary
    """
    service = TrainingService(samples_dir, models_dir)
    return service.train_model(
        num_epochs=num_epochs,
        batch_size=batch_size,
        learning_rate=learning_rate
    )


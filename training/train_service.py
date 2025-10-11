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


class TrainingService:
    """Service for managing OCR model training."""
    
    def __init__(
        self,
        samples_dir: Path = Path("data/training_data/ocr_samples"),
        models_dir: Path = Path("models/ocr_weights"),
        device: Optional[str] = None
    ):
        self.samples_dir = Path(samples_dir)
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        if device is None:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            self.device = device
        
        logger.info(f"Training service initialized")
        logger.info(f"Samples directory: {self.samples_dir}")
        logger.info(f"Models directory: {self.models_dir}")
        logger.info(f"Device: {self.device}")
    
    def count_samples(self) -> int:
        """Count available training samples."""
        if not self.samples_dir.exists():
            return 0
        return len(list(self.samples_dir.glob("*.json")))
    
    def can_train(self, min_samples: int = 10) -> tuple[bool, str]:
        """
        Check if training can proceed.
        
        Returns:
            (can_train, message)
        """
        sample_count = self.count_samples()
        
        if sample_count < min_samples:
            return False, f"Insufficient samples: {sample_count}/{min_samples}"
        
        if not torch.cuda.is_available() and self.device == 'cuda':
            logger.warning("CUDA requested but not available, falling back to CPU")
            self.device = 'cpu'
        
        return True, f"Ready to train with {sample_count} samples"
    
    def prepare_datasets(self, val_ratio: float = 0.2):
        """Prepare train and validation datasets."""
        logger.info("Loading training samples...")
        
        # Load full dataset
        full_dataset = OCRCorrectionDataset(self.samples_dir)
        
        if len(full_dataset) == 0:
            raise ValueError("No valid training samples found")
        
        # Split into train and validation
        train_size = int(len(full_dataset) * (1 - val_ratio))
        val_size = len(full_dataset) - train_size
        
        train_dataset, val_dataset = torch.utils.data.random_split(
            full_dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(42)
        )
        
        # Copy vocabulary to split datasets
        train_dataset.dataset = full_dataset
        val_dataset.dataset = full_dataset
        
        logger.info(f"Dataset split: {train_size} train, {val_size} validation")
        
        return train_dataset, val_dataset, full_dataset.vocab
    
    def train_model(
        self,
        num_epochs: int = 20,
        batch_size: int = 16,
        learning_rate: float = 0.001,
        val_ratio: float = 0.2,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Train OCR model on collected samples.
        
        Args:
            num_epochs: Number of training epochs
            batch_size: Batch size for training
            learning_rate: Learning rate
            val_ratio: Validation set ratio
            progress_callback: Optional callback for progress updates
        
        Returns:
            Training result dictionary
        """
        logger.info("=" * 60)
        logger.info("STARTING OCR MODEL TRAINING")
        logger.info("=" * 60)
        
        # Check if can train
        can_train, message = self.can_train()
        if not can_train:
            raise ValueError(message)
        
        logger.info(f"✅ {message}")
        
        try:
            # Prepare datasets
            train_dataset, val_dataset, vocab = self.prepare_datasets(val_ratio)
            
            # Create model
            logger.info("Creating model...")
            model = SimpleRecognitionModel(
                vocab_size=len(vocab),
                hidden_size=256
            )
            
            total_params = sum(p.numel() for p in model.parameters())
            trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
            logger.info(f"Model parameters: {total_params:,} (trainable: {trainable_params:,})")
            
            # Create trainer
            logger.info("Initializing trainer...")
            trainer = OCRTrainer(
                model=model,
                train_dataset=train_dataset.dataset,
                val_dataset=val_dataset.dataset if val_ratio > 0 else None,
                learning_rate=learning_rate,
                batch_size=batch_size,
                device=self.device
            )
            
            # Train
            logger.info(f"\nStarting training for {num_epochs} epochs...")
            history = trainer.train(
                num_epochs=num_epochs,
                save_dir=self.models_dir,
                save_every=5
            )
            
            # Save final model
            final_model_path = self.models_dir / "latest_model.pth"
            trainer.save_checkpoint(
                path=final_model_path,
                epoch=num_epochs,
                loss=history['train_loss'][-1],
                accuracy=history['val_accuracy'][-1] if history['val_accuracy'] else 0.0
            )
            
            logger.info(f"\n✅ Training completed successfully!")
            logger.info(f"Final model saved to: {final_model_path}")
            
            # Create training report
            report = {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "samples_used": len(train_dataset) + len(val_dataset),
                "train_samples": len(train_dataset),
                "val_samples": len(val_dataset),
                "epochs": num_epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "device": self.device,
                "vocab_size": len(vocab),
                "final_train_loss": history['train_loss'][-1],
                "final_val_loss": history['val_loss'][-1] if history['val_loss'] else None,
                "final_val_accuracy": history['val_accuracy'][-1] if history['val_accuracy'] else None,
                "best_val_accuracy": max(history['val_accuracy']) if history['val_accuracy'] else None,
                "model_path": str(final_model_path),
                "history": history
            }
            
            # Save training report
            report_path = self.models_dir / f"training_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            with report_path.open('w', encoding='utf-8') as f:
                # Convert any non-serializable objects
                serializable_report = {
                    k: v for k, v in report.items() if k != 'history'
                }
                serializable_report['history_summary'] = {
                    'train_loss': [float(x) for x in history['train_loss']],
                    'val_loss': [float(x) for x in history['val_loss']] if history['val_loss'] else [],
                    'val_accuracy': [float(x) for x in history['val_accuracy']] if history['val_accuracy'] else []
                }
                json.dump(serializable_report, f, indent=2)
            
            logger.info(f"Training report saved to: {report_path}")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Training failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
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


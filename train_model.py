#!/usr/bin/env python3
"""
Standalone script to train OCR model on collected samples.
Can be run independently or called from API.
"""

import argparse
import logging
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Train OCR model on collected correction samples'
    )
    parser.add_argument(
        '--samples-dir',
        type=str,
        default='data/training_data/ocr_samples',
        help='Directory containing training samples'
    )
    parser.add_argument(
        '--models-dir',
        type=str,
        default='models/ocr_weights',
        help='Directory to save trained models'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=20,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=16,
        help='Training batch size'
    )
    parser.add_argument(
        '--learning-rate',
        type=float,
        default=0.001,
        help='Learning rate'
    )
    parser.add_argument(
        '--val-ratio',
        type=float,
        default=0.2,
        help='Validation set ratio (0.0-1.0)'
    )
    parser.add_argument(
        '--device',
        type=str,
        choices=['cuda', 'cpu', 'auto'],
        default='auto',
        help='Device to use for training'
    )
    
    args = parser.parse_args()
    
    try:
        from training.train_service import TrainingService
        import torch
        
        logger.info("=" * 70)
        logger.info("OCR MODEL TRAINING")
        logger.info("=" * 70)
        logger.info(f"Samples directory: {args.samples_dir}")
        logger.info(f"Models directory: {args.models_dir}")
        logger.info(f"Epochs: {args.epochs}")
        logger.info(f"Batch size: {args.batch_size}")
        logger.info(f"Learning rate: {args.learning_rate}")
        logger.info(f"Validation ratio: {args.val_ratio}")
        
        # Determine device
        if args.device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            device = args.device
        
        if device == 'cuda' and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, falling back to CPU")
            device = 'cpu'
        
        logger.info(f"Device: {device}")
        
        if device == 'cpu':
            logger.warning("⚠️  Training on CPU will be SLOW. Consider using GPU for faster training.")
        
        logger.info("=" * 70)
        
        # Initialize service
        service = TrainingService(
            samples_dir=Path(args.samples_dir),
            models_dir=Path(args.models_dir),
            device=device
        )
        
        # Check samples
        sample_count = service.count_samples()
        logger.info(f"\n📊 Found {sample_count} training samples")
        
        if sample_count < 10:
            logger.error(f"❌ Insufficient training samples: {sample_count}/10")
            logger.error("   Make more corrections in the UI to collect training data")
            return 1
        
        # Train
        logger.info("\n🚀 Starting training...")
        logger.info("This may take a while depending on sample count and device...")
        logger.info("")
        
        report = service.train_model(
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            val_ratio=args.val_ratio
        )
        
        # Print summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ TRAINING COMPLETED SUCCESSFULLY!")
        logger.info("=" * 70)
        logger.info(f"Training samples used: {report['train_samples']}")
        logger.info(f"Validation samples: {report['val_samples']}")
        logger.info(f"Epochs completed: {report['epochs']}")
        logger.info(f"Final train loss: {report['final_train_loss']:.4f}")
        
        if report['final_val_accuracy']:
            logger.info(f"Final validation accuracy: {report['final_val_accuracy']:.2%}")
            logger.info(f"Best validation accuracy: {report['best_val_accuracy']:.2%}")
        
        logger.info(f"\n📁 Model saved to: {report['model_path']}")
        logger.info(f"📁 Best model: {args.models_dir}/best_model.pth")
        logger.info("")
        logger.info("🎯 Next steps:")
        logger.info("   1. Check training report in models/ocr_weights/")
        logger.info("   2. Test the model on new documents")
        logger.info("   3. Deploy if accuracy is improved")
        logger.info("=" * 70)
        
        return 0
        
    except ImportError as e:
        logger.error("❌ Training dependencies not installed!")
        logger.error(f"   Error: {e}")
        logger.error("")
        logger.error("📦 Install PyTorch:")
        logger.error("   pip install torch torchvision")
        logger.error("")
        logger.error("   Or for CPU-only:")
        logger.error("   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")
        return 1
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())


"""
Training module for OCR model fine-tuning.
"""

from training.doctr_finetuning import (
    OCRCorrectionDataset,
    SimpleRecognitionModel,
    OCRTrainer
)

from training.train_service import (
    TrainingService,
    train_ocr_model
)

__all__ = [
    'OCRCorrectionDataset',
    'SimpleRecognitionModel',
    'OCRTrainer',
    'TrainingService',
    'train_ocr_model'
]


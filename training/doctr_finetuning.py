"""
DocTR Model Fine-tuning Module
Implements real OCR model training on collected correction samples.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
import json
from PIL import Image
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class OCRCorrectionDataset(Dataset):
    """PyTorch Dataset for OCR correction training samples."""
    
    def __init__(self, samples_dir: Path, transform=None):
        """
        Args:
            samples_dir: Directory containing training samples (PNG + JSON pairs)
            transform: Optional image transformations
        """
        self.samples_dir = Path(samples_dir)
        self.transform = transform
        
        # Load all sample metadata
        self.samples = []
        json_files = list(self.samples_dir.glob("*.json"))
        
        logger.info(f"Loading {len(json_files)} training samples from {samples_dir}")
        
        for json_file in json_files:
            try:
                with json_file.open('r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Find corresponding image
                image_file = json_file.with_suffix('.png')
                if not image_file.exists():
                    logger.warning(f"Image not found for {json_file.name}")
                    continue
                
                self.samples.append({
                    'image_path': image_file,
                    'original_text': metadata.get('original_text', ''),
                    'corrected_text': metadata.get('corrected_text', ''),
                    'metadata': metadata
                })
            except Exception as e:
                logger.error(f"Failed to load sample {json_file}: {e}")
        
        logger.info(f"Successfully loaded {len(self.samples)} training samples")
        
        # Build vocabulary from corrected texts
        self.build_vocabulary()
    
    def build_vocabulary(self):
        """Build character vocabulary from training data."""
        chars = set()
        for sample in self.samples:
            chars.update(sample['corrected_text'])
        
        # Add special tokens
        self.vocab = ['<PAD>', '<SOS>', '<EOS>', '<UNK>'] + sorted(list(chars))
        self.char_to_idx = {char: idx for idx, char in enumerate(self.vocab)}
        self.idx_to_char = {idx: char for char, idx in self.char_to_idx.items()}
        
        logger.info(f"Built vocabulary with {len(self.vocab)} characters")
    
    def encode_text(self, text: str) -> List[int]:
        """Convert text to indices using vocabulary."""
        return [self.char_to_idx.get(char, self.char_to_idx['<UNK>']) 
                for char in text]
    
    def decode_indices(self, indices: List[int]) -> str:
        """Convert indices back to text."""
        return ''.join([self.idx_to_char.get(idx, '<UNK>') for idx in indices])
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        """Get a training sample."""
        sample = self.samples[idx]
        
        # Load and preprocess image
        try:
            image = Image.open(sample['image_path']).convert('RGB')
            
            # Resize to standard size for training
            # DocTR typically uses 32 height for text recognition
            target_height = 32
            aspect_ratio = image.width / image.height
            target_width = int(target_height * aspect_ratio)
            image = image.resize((target_width, target_height), Image.LANCZOS)
            
            # Convert to tensor
            image_array = np.array(image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_array).permute(2, 0, 1)
            
            if self.transform:
                image_tensor = self.transform(image_tensor)
            
            # Encode target text
            target_text = sample['corrected_text']
            target_indices = self.encode_text(target_text)
            target_tensor = torch.LongTensor(target_indices)
            
            return {
                'image': image_tensor,
                'target': target_tensor,
                'target_text': target_text,
                'original_text': sample['original_text'],
                'target_length': len(target_indices)
            }
        except Exception as e:
            logger.error(f"Error loading sample {idx}: {e}")
            # Return a dummy sample to avoid breaking the batch
            return {
                'image': torch.zeros(3, 32, 100),
                'target': torch.LongTensor([0]),
                'target_text': '',
                'original_text': '',
                'target_length': 1
            }


def collate_fn(batch):
    """Custom collate function to handle variable-length sequences and images."""
    # Pad images to same width
    max_width = max(item['image'].shape[2] for item in batch)
    padded_images = []
    
    for item in batch:
        image = item['image']
        # Get current dimensions [C, H, W]
        c, h, w = image.shape
        
        # Pad width if needed
        if w < max_width:
            padding = max_width - w
            # Pad on the right side with zeros (black)
            padded = torch.nn.functional.pad(image, (0, padding, 0, 0, 0, 0))
        else:
            padded = image
        
        padded_images.append(padded)
    
    images = torch.stack(padded_images)
    
    # Pad targets to same length
    max_length = max(item['target_length'] for item in batch)
    targets = []
    target_lengths = []
    
    for item in batch:
        target = item['target']
        padding = max_length - len(target)
        if padding > 0:
            target = torch.cat([target, torch.zeros(padding, dtype=torch.long)])
        targets.append(target)
        target_lengths.append(item['target_length'])
    
    targets = torch.stack(targets)
    target_lengths = torch.LongTensor(target_lengths)
    
    return {
        'images': images,
        'targets': targets,
        'target_lengths': target_lengths,
        'target_texts': [item['target_text'] for item in batch],
        'original_texts': [item['original_text'] for item in batch]
    }


class SimpleRecognitionModel(nn.Module):
    """
    Simplified recognition model for fine-tuning.
    In production, you'd use DocTR's actual recognition model.
    """
    
    def __init__(self, vocab_size: int, hidden_size: int = 256):
        super().__init__()
        
        # CNN feature extractor
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 256, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.3)
        
        # After 3 pooling layers (2x2), height: 32 -> 16 -> 8 -> 4
        # Features: 256 channels * 4 height = 1024
        cnn_output_features = 256 * 4  # channels * final_height
        
        # LSTM for sequence modeling
        self.lstm = nn.LSTM(
            input_size=cnn_output_features,  # 1024
            hidden_size=hidden_size,
            num_layers=2,
            bidirectional=True,
            batch_first=True,
            dropout=0.3
        )
        
        # Output projection
        self.fc = nn.Linear(hidden_size * 2, vocab_size)
    
    def forward(self, x):
        """
        Args:
            x: Input images [batch, 3, height, width]
        Returns:
            logits: [batch, sequence_length, vocab_size]
        """
        # CNN feature extraction
        x = self.relu(self.conv1(x))
        x = self.pool(x)
        x = self.dropout(x)
        
        x = self.relu(self.conv2(x))
        x = self.pool(x)
        x = self.dropout(x)
        
        x = self.relu(self.conv3(x))
        x = self.pool(x)
        x = self.dropout(x)
        
        # Reshape for LSTM: [batch, channels, height, width] -> [batch, width, channels*height]
        batch_size, channels, height, width = x.size()
        
        # After 3 pooling layers (2x2), height should be 32/8 = 4
        # Width varies based on input
        x = x.permute(0, 3, 1, 2)  # [batch, width, channels, height]
        x = x.reshape(batch_size, width, channels * height)
        
        # LSTM sequence modeling
        # x: [batch, sequence_length, features]
        x, _ = self.lstm(x)
        
        # Output projection
        logits = self.fc(x)
        
        return logits


class OCRTrainer:
    """Handles OCR model training, validation, and checkpointing."""
    
    def __init__(
        self,
        model: nn.Module,
        train_dataset: OCRCorrectionDataset,
        val_dataset: Optional[OCRCorrectionDataset] = None,
        learning_rate: float = 0.001,
        batch_size: int = 16,
        device: str = 'cuda' if torch.cuda.is_available() else 'cpu'
    ):
        self.model = model.to(device)
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.device = device
        self.batch_size = batch_size
        
        # Data loaders
        self.train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=collate_fn,
            num_workers=0  # Set to 0 for Windows compatibility
        )
        
        if val_dataset:
            self.val_loader = DataLoader(
                val_dataset,
                batch_size=batch_size,
                shuffle=False,
                collate_fn=collate_fn,
                num_workers=0
            )
        
        # Optimizer and loss
        self.optimizer = optim.Adam(model.parameters(), lr=learning_rate)
        self.criterion = nn.CTCLoss(blank=0, zero_infinity=True)
        
        # Training history
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'val_accuracy': []
        }
        
        logger.info(f"Trainer initialized on device: {device}")
        logger.info(f"Training samples: {len(train_dataset)}")
        if val_dataset:
            logger.info(f"Validation samples: {len(val_dataset)}")
    
    def train_epoch(self) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0
        num_batches = 0
        
        for batch in self.train_loader:
            images = batch['images'].to(self.device)
            targets = batch['targets'].to(self.device)
            target_lengths = batch['target_lengths']
            
            # Forward pass
            self.optimizer.zero_grad()
            logits = self.model(images)
            
            # Prepare for CTC loss
            # CTC expects: [time, batch, num_classes]
            logits = logits.permute(1, 0, 2)
            log_probs = torch.nn.functional.log_softmax(logits, dim=2)
            
            input_lengths = torch.full(
                size=(logits.size(1),),
                fill_value=logits.size(0),
                dtype=torch.long
            )
            
            # Compute loss
            loss = self.criterion(log_probs, targets, input_lengths, target_lengths)
            
            # Backward pass
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=5.0)
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        avg_loss = total_loss / max(num_batches, 1)
        return avg_loss
    
    def validate(self) -> Tuple[float, float]:
        """Validate the model."""
        if not self.val_dataset:
            return 0.0, 0.0
        
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0
        num_batches = 0
        
        with torch.no_grad():
            for batch in self.val_loader:
                images = batch['images'].to(self.device)
                targets = batch['targets'].to(self.device)
                target_lengths = batch['target_lengths']
                target_texts = batch['target_texts']
                
                # Forward pass
                logits = self.model(images)
                
                # CTC loss
                logits_ctc = logits.permute(1, 0, 2)
                log_probs = torch.nn.functional.log_softmax(logits_ctc, dim=2)
                input_lengths = torch.full(
                    size=(logits_ctc.size(1),),
                    fill_value=logits_ctc.size(0),
                    dtype=torch.long
                )
                
                loss = self.criterion(log_probs, targets, input_lengths, target_lengths)
                total_loss += loss.item()
                
                # Decode predictions
                predictions = torch.argmax(logits, dim=2)
                for i, pred_indices in enumerate(predictions):
                    pred_text = self.decode_prediction(pred_indices.cpu().numpy())
                    if pred_text == target_texts[i]:
                        correct += 1
                    total += 1
                
                num_batches += 1
        
        avg_loss = total_loss / max(num_batches, 1)
        accuracy = correct / max(total, 1)
        
        return avg_loss, accuracy
    
    def decode_prediction(self, indices: np.ndarray) -> str:
        """Decode CTC output to text."""
        # Remove duplicates and blanks
        prev_idx = -1
        decoded = []
        for idx in indices:
            if idx != 0 and idx != prev_idx:  # 0 is blank token
                if idx < len(self.train_dataset.vocab):
                    decoded.append(self.train_dataset.vocab[idx])
            prev_idx = idx
        return ''.join(decoded)
    
    def train(
        self,
        num_epochs: int,
        save_dir: Path,
        save_every: int = 5
    ) -> Dict:
        """
        Train the model for specified epochs.
        
        Args:
            num_epochs: Number of training epochs
            save_dir: Directory to save checkpoints
            save_every: Save checkpoint every N epochs
        
        Returns:
            Training history dictionary
        """
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        best_val_loss = float('inf')
        
        logger.info(f"Starting training for {num_epochs} epochs")
        logger.info(f"Device: {self.device}")
        logger.info(f"Batch size: {self.batch_size}")
        
        for epoch in range(1, num_epochs + 1):
            logger.info(f"\nEpoch {epoch}/{num_epochs}")
            logger.info("-" * 50)
            
            # Train
            train_loss = self.train_epoch()
            self.history['train_loss'].append(train_loss)
            logger.info(f"Train Loss: {train_loss:.4f}")
            
            # Validate
            if self.val_dataset:
                val_loss, val_accuracy = self.validate()
                self.history['val_loss'].append(val_loss)
                self.history['val_accuracy'].append(val_accuracy)
                logger.info(f"Val Loss: {val_loss:.4f}, Val Accuracy: {val_accuracy:.2%}")
                
                # Save best model
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    checkpoint_path = save_dir / "best_model.pth"
                    self.save_checkpoint(checkpoint_path, epoch, val_loss, val_accuracy)
                    logger.info(f"✅ Saved best model (val_loss: {val_loss:.4f})")
            
            # Regular checkpoint
            if epoch % save_every == 0:
                checkpoint_path = save_dir / f"checkpoint_epoch_{epoch}.pth"
                self.save_checkpoint(checkpoint_path, epoch, train_loss, 0.0)
                logger.info(f"💾 Saved checkpoint: {checkpoint_path}")
        
        logger.info("\n" + "=" * 50)
        logger.info("Training completed!")
        logger.info(f"Best validation loss: {best_val_loss:.4f}")
        
        return self.history
    
    def save_checkpoint(
        self,
        path: Path,
        epoch: int,
        loss: float,
        accuracy: float
    ):
        """Save model checkpoint."""
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'loss': loss,
            'accuracy': accuracy,
            'vocab': self.train_dataset.vocab,
            'char_to_idx': self.train_dataset.char_to_idx,
            'history': self.history,
            'timestamp': datetime.utcnow().isoformat()
        }
        torch.save(checkpoint, path)
    
    def load_checkpoint(self, path: Path):
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.history = checkpoint.get('history', self.history)
        logger.info(f"Loaded checkpoint from epoch {checkpoint['epoch']}")
        return checkpoint


def create_train_val_split(
    samples_dir: Path,
    val_ratio: float = 0.2
) -> Tuple[List[Path], List[Path]]:
    """Split samples into train and validation sets."""
    json_files = list(samples_dir.glob("*.json"))
    
    # Shuffle
    import random
    random.shuffle(json_files)
    
    # Split
    split_idx = int(len(json_files) * (1 - val_ratio))
    train_files = json_files[:split_idx]
    val_files = json_files[split_idx:]
    
    return train_files, val_files


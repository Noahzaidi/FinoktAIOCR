# 📚 Training Samples Guide

## What Are Training Samples?

Training samples are **word-level image crops paired with their corrections** that the system automatically collects when you make corrections in the UI. These samples can be used to fine-tune the OCR model to improve its accuracy over time.

> **🔧 Fixed:** Training sample creation was missing in the original code. Now properly implemented and working!

## How Training Samples Are Created

### Automatic Collection Process

Every time you **save a correction** in the review UI:

1. **Image Cropping**: System crops the word region from the original document page
2. **Metadata Storage**: Saves both the original OCR text and your corrected text
3. **File Creation**: Creates 2 files per correction:
   - `{doc_id}_{word_id}_{timestamp}.png` - Cropped word image
   - `{doc_id}_{word_id}_{timestamp}.json` - Metadata with correction details

### Storage Location

```
data/
└── training_data/
    └── ocr_samples/
        ├── abc123_p0_w5_20250111_143022.png
        ├── abc123_p0_w5_20250111_143022.json
        ├── abc123_p0_w12_20250111_143045.png
        └── abc123_p0_w12_20250111_143045.json
```

### Metadata Format

Each JSON file contains:

```json
{
  "document_id": "abc123",
  "page": 0,
  "word_id": "p0_w5",
  "original_text": "lnvoice",
  "corrected_text": "Invoice",
  "timestamp": "2025-01-11T14:30:22.123456"
}
```

## How to Generate Training Samples

### Step-by-Step Process

**1. Upload a Document**
```
Navigate to http://localhost:8000/upload
→ Choose a PDF or image file
→ Click "Upload and Process"
```

**2. Review the OCR Results**
```
System automatically redirects to review page
→ Document is displayed with bounding boxes
```

**3. Make Corrections**
```
a) Click on any red bounding box in the document viewer
b) In the "Edit Selection" tab, modify the text
c) Click "Save Correction"
```

**4. Training Sample Created! ✅**
```
✓ Word image cropped and saved
✓ Correction metadata logged
✓ Counter increments in "Learning Stats" tab
```

### Quick Example

```
Upload invoice.pdf
→ OCR reads "lnvoice" (incorrect)
→ Click on "lnvoice" box
→ Change to "Invoice"
→ Save
→ Training sample created: 
   • invoice_p0_w1_20250111_143022.png
   • invoice_p0_w1_20250111_143022.json
```

## Monitoring Training Samples

### Check Sample Count

**Method 1: Learning Stats Tab**
```
1. Open any document review page
2. Click "Learning Stats" tab
3. See "Training Samples Collected" counter
```

**Method 2: API Endpoint**
```bash
curl http://localhost:8000/api/training_data/stats
```

Response:
```json
{
  "total_samples": 15,
  "status": "success"
}
```

**Method 3: File System**
```bash
# Count PNG files (one per sample)
ls data/training_data/ocr_samples/*.png | wc -l
```

## Model Retraining

### When Can You Retrain?

**Minimum Requirements:**
- ✅ At least 10 training samples
- ✅ Samples from diverse documents (recommended)
- ✅ Mix of different error types (recommended)

### How to Retrain

**1. Via UI (Learning Stats Tab)**
```
Navigate to any document review page
→ Click "Learning Stats" tab
→ Scroll to "🔄 Advanced" section
→ Check sample count
→ Click "Start Model Retraining" (enabled when ≥10 samples)
```

**2. Via API**
```bash
curl -X POST http://localhost:8000/api/retrain_stub
```

### What Happens During Retraining?

**Current Implementation (Stub):**
- Validates sample count (≥10 required)
- Creates retraining log
- Simulates training process

**Future Full Implementation:**
- Loads training samples
- Fine-tunes DocTR model on corrections
- Saves updated model weights
- Validates improved accuracy
- Deploys new model

### Retraining Output

Retraining creates a log file:
```
models/
└── ocr_weights/
    └── retraining_log_20250111_143500.json
```

Log contents:
```json
{
  "timestamp": "2025-01-11T14:35:00.123456",
  "samples_used": 15,
  "status": "completed_stub",
  "model_version": "v1.0_stub",
  "notes": "This is a stub implementation. Real retraining would fine-tune DocTR here."
}
```

## Best Practices

### Quality Over Quantity

**Do:**
- ✅ Correct genuine OCR errors
- ✅ Focus on recurring mistakes
- ✅ Correct different document types
- ✅ Maintain consistency in corrections

**Don't:**
- ❌ Make random/inconsistent corrections
- ❌ Correct already-accurate text
- ❌ Use only one document type
- ❌ Rush through corrections

### Sample Diversity

Aim for corrections across:
- Different document types (invoices, receipts, contracts)
- Various fonts and layouts
- Multiple error patterns (OCR confusion like "l" vs "I")
- Different confidence levels

### Optimal Workflow

```
1. Process 5-10 documents
2. Correct 2-3 errors per document
3. Accumulate 15-20 training samples
4. Trigger retraining
5. Upload new document to test improvements
6. Repeat cycle
```

## Troubleshooting

### "0 training samples available"

**Causes:**
- No corrections made yet
- Training directory doesn't exist
- Permissions issue

**Solutions:**
```bash
# Verify directory exists
mkdir -p data/training_data/ocr_samples

# Check for samples
ls -la data/training_data/ocr_samples/

# Make corrections in UI to generate samples
```

### "Insufficient training data" error

**Issue:** Less than 10 samples when attempting retraining

**Solution:**
- Make more corrections (each correction = 1 sample)
- Need at least 10 corrections across your documents
- Check sample count in Learning Stats tab

### Samples not incrementing

**Possible causes:**
1. Image file not found
2. Invalid bounding box coordinates
3. Permissions issue

**Check logs:**
```bash
# Look for training data preparation messages
grep "Training data prepared" data/logs/*.log
grep "training data preparation" data/logs/*.log
```

## Technical Details

### Image Cropping Logic

```python
# Coordinates are relative [0,1]
# Converted to absolute with 5px padding
abs_x1 = max(0, int(x1 * img_width) - 5)
abs_y1 = max(0, int(y1 * img_height) - 5)
abs_x2 = min(img_width, int(x2 * img_width) + 5)
abs_y2 = min(img_height, int(y2 * img_height) + 5)

# Crop and save
word_image = img.crop((abs_x1, abs_y1, abs_x2, abs_y2))
word_image.save(image_path)
```

### File Naming Convention

```
Format: {doc_id}_{word_id}_{timestamp}.{ext}

Examples:
- abc123_p0_w5_20250111_143022.png
- def456_p1_w12_20250111_150945.json

Components:
- doc_id: Unique document identifier
- word_id: Page and word index (p0_w5 = page 0, word 5)
- timestamp: YYYYmmdd_HHMMSS format
- ext: png for images, json for metadata
```

## Future Enhancements

### Planned Features

1. **Batch Retraining**: Automatically retrain when threshold reached
2. **Training Analytics**: Visualize improvement over time
3. **Sample Quality Scoring**: Rank samples by training value
4. **Active Learning**: System suggests which words to correct
5. **A/B Testing**: Compare old vs new model accuracy
6. **Export/Import**: Share training datasets between instances

### Advanced Retraining

Future full implementation will:
- Use PyTorch/TensorFlow for fine-tuning
- Implement learning rate scheduling
- Add validation split for accuracy testing
- Support incremental learning
- Enable model versioning and rollback

## Summary

**Key Points:**
- ✅ Training samples = automatic by-product of corrections
- ✅ Each correction creates 1 sample (image + metadata)
- ✅ Stored in `data/training_data/ocr_samples/`
- ✅ Need 10+ samples to retrain
- ✅ Check count in "Learning Stats" tab
- ✅ More samples = better model improvement potential

**Quick Start:**
```
1. Upload document
2. Make 10+ corrections
3. Check Learning Stats shows "10+"
4. Click "Start Model Retraining"
5. Done! ✨
```


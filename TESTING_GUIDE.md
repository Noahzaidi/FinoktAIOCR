# 🧪 FinoktAI OCR System - Testing Guide

## 🚀 Quick Start Testing

### 1. Start the Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Open in Browser
Navigate to: `http://localhost:8000`

## 📋 Testing Scenarios

### Scenario 1: Basic OCR and Correction Flow
**Goal**: Test the complete correction workflow

**Steps**:
1. **Upload a Document**
   - Go to `http://localhost:8000`
   - Upload any PDF or image file (invoice, receipt, etc.)
   - Wait for processing to complete

2. **Review OCR Results**
   - You'll be redirected to the review page
   - See bounding boxes overlaid on the document
   - Notice the document type classification at the top

3. **Test Interactive Features**
   - **Hover**: Move mouse over red bounding boxes to see tooltips
   - **Click**: Click any bounding box to select it for editing
   - **Edit**: Change the text in the left panel and click "Save Correction"

4. **Verify Corrections**
   - Watch for "Saved!" message
   - See the corrected text update in both views
   - Check if lexicon learning triggers after multiple corrections

### Scenario 2: Lexicon Learning System
**Goal**: Test automatic correction learning

**Steps**:
1. **Make the Same Correction 3 Times**
   - Upload 3 different documents (or same document multiple times)
   - Make the same text correction (e.g., "Arnount" → "Amount") on each
   - On the 3rd correction, you should see "Lexicon updated" message

2. **Verify Auto-Correction**
   - Upload a new document with the same error
   - The system should automatically apply the learned correction
   - Check the "Learning Stats" tab to see lexicon entries

### Scenario 3: Document Type Classification
**Goal**: Test document type detection

**Test Documents**:
- **Invoice**: Document with "Invoice", "Amount Due", "Invoice Number"
- **Receipt**: Document with "Receipt", "Total Paid", "Change"
- **ID Document**: Document with "Passport", "Driver License", "Date of Birth"

**Expected Results**:
- Document type badge shows correct classification
- Confidence score appears next to document type
- Different document types get different colored badges

### Scenario 4: Learning Analytics
**Goal**: Test the learning dashboard

**Steps**:
1. **Make Several Corrections** (at least 5-10 across different documents)
2. **Go to Learning Stats Tab**
   - See lexicon statistics
   - View training data counts
   - Check recent corrections and training samples
3. **Test Retraining Stub**
   - Click "Start Retraining (Stub)" button
   - Should see success message with sample count

### Scenario 5: Training Data Preparation
**Goal**: Verify training data collection

**Steps**:
1. **Make Corrections** on different words
2. **Check File System**:
   ```bash
   ls -la data/training_data/ocr_samples/
   ```
   - Should see cropped word images (`.png` files)
   - Should see corresponding metadata (`.json` files)

3. **Verify Training Stats API**:
   - Visit: `http://localhost:8000/api/training_data/stats`
   - Should show sample counts and recent samples

## 🔧 API Testing

### Test Individual Endpoints

1. **Document Classification**:
   ```bash
   curl http://localhost:8000/api/document_types
   ```

2. **Lexicon Data**:
   ```bash
   curl http://localhost:8000/api/lexicon
   ```

3. **Training Stats**:
   ```bash
   curl http://localhost:8000/api/training_data/stats
   ```

4. **Document-Specific Classification**:
   ```bash
   curl http://localhost:8000/api/document_classification/{doc_id}
   ```

## 🎯 Expected Behaviors

### ✅ Successful Tests Should Show:

1. **UI Interactions**:
   - Smooth bounding box overlays
   - Responsive hover tooltips
   - Click selection works
   - Text editing updates both views

2. **Learning System**:
   - Corrections saved with timestamps
   - Lexicon updates after 3+ identical corrections
   - Auto-corrections applied on new documents
   - Training data files generated

3. **Document Classification**:
   - Correct document type detection (70%+ accuracy expected)
   - Appropriate confidence scores
   - Type-specific processing

4. **Analytics Dashboard**:
   - Real-time statistics updates
   - Proper lexicon and training data counts
   - Recent activity tracking

### ❌ Troubleshooting Common Issues

1. **Bounding Boxes Not Showing**:
   - Check browser console for JavaScript errors
   - Verify OCR data is loading correctly
   - Try refreshing the page

2. **Corrections Not Saving**:
   - Check network tab for failed API calls
   - Verify file permissions in `data/` directory
   - Check server logs for errors

3. **Classification Not Working**:
   - Ensure document has recognizable text
   - Check if document type keywords are present
   - Try with different document types

4. **Training Data Not Generated**:
   - Verify PIL (Pillow) is installed correctly
   - Check if page images exist in `data/outputs/`
   - Ensure write permissions to `data/training_data/`

## 📊 Performance Testing

### Load Testing
```bash
# Test with multiple documents simultaneously
for i in {1..5}; do
    curl -X POST -F "file=@test_document.pdf" http://localhost:8000/upload &
done
wait
```

### Memory Usage
- Monitor system memory while processing large documents
- Check for memory leaks during extended use

## 🔍 Debugging Tools

### Enable Debug Logging
Add to `main.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Browser Developer Tools
- **Console**: Check for JavaScript errors
- **Network**: Monitor API calls and responses
- **Elements**: Inspect DOM changes

### File System Monitoring
Watch for file creation:
```bash
# Windows
dir /s data\
# Check specific directories
dir data\logs\corrections\
dir data\lexicons\
dir data\training_data\ocr_samples\
```

## 📈 Success Metrics

### Functional Tests ✅
- [ ] Document upload and OCR processing works
- [ ] Bounding box overlay displays correctly
- [ ] Click selection and editing functions
- [ ] Corrections save successfully
- [ ] Lexicon learning triggers after 3+ corrections
- [ ] Document type classification works
- [ ] Training data files are generated
- [ ] Learning analytics display correctly

### Performance Tests ✅
- [ ] Page loads within 3 seconds
- [ ] OCR processing completes within reasonable time
- [ ] UI remains responsive during corrections
- [ ] Memory usage stays stable

### User Experience Tests ✅
- [ ] Intuitive correction workflow
- [ ] Clear visual feedback
- [ ] Error messages are helpful
- [ ] Learning progress is visible

## 🎉 Sample Test Documents

Create test documents with these characteristics:

### Invoice Test Document
```
INVOICE
Invoice Number: INV-12345
Date: 2024-01-15
Amount Due: $1,250.00
```

### Receipt Test Document  
```
RECEIPT
Store: Test Store
Total Paid: $45.99
Change: $4.01
Thank you for your business!
```

### ID Document Test
```
DRIVER LICENSE
Name: John Doe
Date of Birth: 01/15/1990
License Number: DL123456789
```

## 🚨 Known Limitations

1. **OCR Accuracy**: Depends on document quality and DocTR model
2. **Classification**: Simple keyword-based, may misclassify complex documents
3. **Retraining**: Currently a stub - doesn't actually retrain models
4. **Scalability**: File-based storage, not suitable for high-volume production

## 📞 Getting Help

If you encounter issues:
1. Check the server logs in the terminal
2. Inspect browser console for JavaScript errors
3. Verify file permissions in the `data/` directory
4. Ensure all dependencies are installed correctly

Happy testing! 🎯

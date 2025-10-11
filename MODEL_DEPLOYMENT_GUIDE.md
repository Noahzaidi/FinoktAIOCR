# 🚀 Model Deployment Guide

## Overview

After training your OCR model, you need to **deploy** it to actually use it in production. This guide covers both UI-based and CLI-based deployment.

---

## ✅ **Recommended: UI-Based Deployment**

### **Why UI Deployment is Better:**

- ✅ **Visual interface** - See all available models
- ✅ **One-click deployment** - No command line needed
- ✅ **Safety features** - Confirmation dialogs
- ✅ **Rollback capability** - Easy to undo
- ✅ **Deployment history** - Track all changes
- ✅ **Real-time status** - Instant feedback

---

## 🖥️ **How to Deploy via UI**

### **Step 1: Train a Model**

```bash
python train_model.py --epochs 20
```

Wait for training to complete (~15-30 minutes on CPU).

### **Step 2: Open the Deployment UI**

1. Go to any document review page: `http://localhost:8000/canvas/{doc_id}`
2. Click **"Learning Stats"** tab
3. Scroll to **"🚀 Model Deployment"** section

### **Step 3: View Available Models**

You'll see:

```
┌─────────────────────────────────────────────┐
│ Active Model:                               │
│ No model deployed yet                       │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Available Models:                           │
├─────────────────────────────────────────────┤
│ best_model.pth [BEST]                       │
│ Epoch 15 | Loss: 3.1234 | Acc: 66.7%      │
│ 49.5 MB                    [🚀 Deploy]      │
├─────────────────────────────────────────────┤
│ latest_model.pth [LATEST]                   │
│ Epoch 20 | Loss: 3.2224 | Acc: 0.0%       │
│ 49.5 MB                    [🚀 Deploy]      │
└─────────────────────────────────────────────┘
```

### **Step 4: Deploy the Best Model**

1. Click **🚀 Deploy** next to `best_model.pth`
2. Confirm deployment dialog
3. Wait for success message
4. Model is now active!

### **After Deployment:**

```
┌─────────────────────────────────────────────┐
│ Active Model:                               │
│ Model: Active (deployed)                    │
│ Epoch: 15                                   │
│ Accuracy: 66.7%                             │
│ Deployed: 10/11/2025, 5:51:33 PM          │
└─────────────────────────────────────────────┘
```

---

## 📊 **Which Model Should You Deploy?**

### **Recommendation:**

**✅ Deploy `best_model.pth`**

This is the model with the **lowest validation loss** during training, which typically means:
- Better generalization
- More accurate on unseen data
- Less overfitting

### **Understanding the Models:**

| Model | When to Use |
|-------|-------------|
| **best_model.pth** | ✅ **Production** - Best validation performance |
| **latest_model.pth** | Testing - Last epoch (might be overfit) |
| **checkpoint_epoch_X.pth** | Debugging - Specific epoch checkpoints |

---

## 🔄 **Rollback Feature**

### **When to Rollback:**

- New model performs worse
- Unexpected errors after deployment
- Need to revert quickly

### **How to Rollback (UI):**

1. Go to Learning Stats → Model Deployment
2. Click **↩️ Rollback** button
3. Confirm rollback
4. Previous model restored!

### **How to Rollback (CLI):**

```bash
python deploy_model.py rollback
```

---

## 💻 **Alternative: CLI-Based Deployment**

### **List Available Models:**

```bash
python deploy_model.py list
```

Output:
```
======================================================================
AVAILABLE MODELS (6 total)
======================================================================

1. best_model.pth [BEST]
   Epoch: 15
   Loss: 3.1234
   Accuracy: 66.7%
   Size: 49.50 MB
   Created: 2025-01-11T15:51:33.123456

2. latest_model.pth [LATEST]
   Epoch: 20
   Loss: 3.2224
   Accuracy: 0.0%
   Size: 49.50 MB
   Created: 2025-01-11T15:51:33.123456
```

### **Deploy a Model:**

```bash
python deploy_model.py deploy best_model.pth --notes "First production deployment"
```

Output:
```
2025-01-11 17:51:33 - INFO - ============================================================
2025-01-11 17:51:33 - INFO - DEPLOYING OCR MODEL
2025-01-11 17:51:33 - INFO - ============================================================
2025-01-11 17:51:33 - INFO - Source model: models/ocr_weights/best_model.pth
2025-01-11 17:51:33 - INFO - Deployed by: cli
2025-01-11 17:51:33 - INFO - ✅ Backed up current model to: models/deployed/backup_20251011_175133.pth
2025-01-11 17:51:33 - INFO - ✅ Copied model to: models/deployed/deployed_20251011_175133.pth
2025-01-11 17:51:33 - INFO - ✅ Updated active model link
2025-01-11 17:51:33 - INFO - ============================================================
2025-01-11 17:51:33 - INFO - ✅ DEPLOYMENT COMPLETED SUCCESSFULLY
2025-01-11 17:51:33 - INFO - ============================================================
2025-01-11 17:51:33 - INFO - Active model: models/deployed/active_model.pth
2025-01-11 17:51:33 - INFO - Model epoch: 15
2025-01-11 17:51:33 - INFO - Model accuracy: 66.70%
```

### **Check Active Model:**

```bash
python deploy_model.py active
```

### **View Deployment History:**

```bash
python deploy_model.py history --limit 5
```

---

## 📁 **What Happens During Deployment**

### **File Structure:**

```
models/
├── ocr_weights/              # Trained models
│   ├── best_model.pth        # Your trained model
│   ├── latest_model.pth
│   └── checkpoint_*.pth
│
└── deployed/                 # Production models
    ├── active_model.pth      # ← ACTIVE (symlink/copy)
    ├── deployed_20251011_175133.pth
    ├── backup_20251011_175133.pth
    └── deployment_history.json
```

### **Deployment Process:**

```
1. Backup current active model (if exists)
   → models/deployed/backup_{timestamp}.pth

2. Copy new model to deployed directory
   → models/deployed/deployed_{timestamp}.pth

3. Update active model link
   → models/deployed/active_model.pth

4. Record deployment in history
   → models/deployed/deployment_history.json

5. Log deployment event
```

---

## 🎯 **Deployment Workflow**

### **Complete Process:**

```
┌─────────────────────────────────────┐
│ 1. Collect 50+ corrections          │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 2. Train model                      │
│    python train_model.py --epochs 30│
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 3. Review training report           │
│    Check accuracy, loss             │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 4. Deploy via UI or CLI             │
│    UI: Learning Stats → Deploy      │
│    CLI: python deploy_model.py ...  │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 5. Test on new documents            │
│    Upload & verify improvements     │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 6. Monitor performance              │
│    If good: Keep                    │
│    If bad: Rollback                 │
└─────────────────────────────────────┘
```

---

## ⚠️ **Important Notes**

### **Before Deploying:**

1. ✅ **Check training report** - Ensure model trained well
2. ✅ **Review validation accuracy** - Should be >60% for small datasets
3. ✅ **Test on a few documents** - Manual verification
4. ✅ **Backup important data** - Just in case

### **After Deploying:**

1. ✅ **Test immediately** - Upload a document and check OCR quality
2. ✅ **Compare with baseline** - Is it better than before?
3. ✅ **Monitor errors** - Watch for new issues
4. ✅ **Keep rollback option ready** - Easy to undo

### **Safety Features:**

- ✅ **Automatic backup** - Previous model always saved
- ✅ **One-click rollback** - Easy to restore
- ✅ **Deployment history** - Track all changes
- ✅ **Confirmation dialogs** - Prevent accidents

---

## 🔍 **Verifying Deployment**

### **Method 1: Check Files**

```bash
# View active model
ls -lh models/deployed/active_model.pth

# View all deployed models
ls -lh models/deployed/
```

### **Method 2: Check UI**

1. Go to Learning Stats tab
2. Look at "Active Model" section
3. Should show deployed model info

### **Method 3: API Check**

```bash
curl http://localhost:8000/api/models/available
```

---

## 🎓 **Best Practices**

### **Deployment Strategy:**

#### **For Production:**

1. **Train with 50+ samples** minimum
2. **Achieve 80%+ validation accuracy**
3. **Test thoroughly** before deployment
4. **Deploy during low-traffic** periods
5. **Monitor for 24 hours** after deployment
6. **Keep previous model** for quick rollback

#### **For Development:**

1. **Deploy frequently** to test
2. **A/B test** old vs new models
3. **Collect metrics** on performance
4. **Iterate quickly** - train → deploy → test → repeat

### **Version Control:**

```
Week 1: baseline (no deployment)
Week 2: v1.0 (first 20 samples, 65% acc)
Week 3: v1.1 (50 samples, 78% acc) ✅ Deploy
Week 4: v1.2 (100 samples, 85% acc) ✅ Deploy
```

---

## 🐛 **Troubleshooting**

### **"No model deployed yet"**

**Solution:**
```bash
# Deploy your trained model
python deploy_model.py deploy best_model.pth
```

### **"Model not found"**

**Cause:** Model filename doesn't exist

**Solution:**
```bash
# List available models first
python deploy_model.py list

# Then deploy by exact filename
python deploy_model.py deploy best_model.pth
```

### **"No previous deployment found to rollback to"**

**Cause:** This is your first deployment

**Solution:** Can't rollback on first deployment. Deploy will work forward.

---

## 📊 **Monitoring After Deployment**

### **What to Watch:**

1. **OCR Accuracy** - Are results better?
2. **Processing Speed** - Any performance impact?
3. **Error Rate** - Fewer mistakes?
4. **User Feedback** - What do users say?

### **Metrics to Track:**

```python
# Before deployment
baseline_accuracy = 85%
baseline_errors = 150/1000 words

# After deployment
new_accuracy = 91%  # ✅ Improvement!
new_errors = 90/1000 words  # ✅ 40% reduction!
```

---

## 🔄 **Deployment Lifecycle**

### **Typical Timeline:**

```
Day 1: Deploy new model
     ↓
Day 1-7: Monitor closely
     ↓
Week 2: Collect feedback
     ↓
Week 3-4: Decide:
  → If good: Keep deployed
  → If bad: Rollback & retrain
     ↓
Week 5: Train v2 with more data
     ↓
Repeat cycle...
```

### **Continuous Improvement:**

```
Version 1.0 → Deploy → Test → Feedback
              ↓
         Collect more corrections (50 samples)
              ↓
Version 1.1 → Deploy → Test → Feedback
              ↓
         Collect more corrections (100 samples)
              ↓
Version 1.2 → Deploy → Test → Better!
```

---

## 🎯 **Quick Reference**

### **UI Commands:**

| Action | Where | Button |
|--------|-------|--------|
| Deploy model | Learning Stats → Model Deployment | 🚀 Deploy |
| Rollback | Learning Stats → Model Deployment | ↩️ Rollback |
| Refresh list | Learning Stats → Model Deployment | 🔄 Refresh |
| View history | Learning Stats → Model Deployment | (automatic) |

### **CLI Commands:**

```bash
# List models
python deploy_model.py list

# Deploy
python deploy_model.py deploy best_model.pth

# Check active
python deploy_model.py active

# Rollback
python deploy_model.py rollback

# View history
python deploy_model.py history
```

---

## 💡 **Pro Tips**

### **1. Always Deploy "best_model.pth" First**

This has the best validation performance.

### **2. Test Before Full Deployment**

- Deploy to staging/test environment first
- Upload 5-10 documents
- Verify accuracy
- Then deploy to production

### **3. Keep Deployment Notes**

```bash
python deploy_model.py deploy best_model.pth \
  --notes "Trained on 50 invoice corrections, 78% acc, ready for production"
```

### **4. Monitor the First Hour**

- Watch for errors
- Check OCR quality
- Be ready to rollback

### **5. Version Your Models**

Keep checkpoints:
- `model_v1.0.pth` - First production
- `model_v1.1.pth` - After 50 more samples
- `model_v2.0.pth` - Major improvement

---

## 🎉 **Summary**

### **What You Can Do Now:**

✅ **Train** models with PyTorch (`python train_model.py`)
✅ **Deploy** via beautiful UI (one-click)
✅ **Deploy** via CLI for automation
✅ **Rollback** if something goes wrong
✅ **Track history** of all deployments
✅ **Compare models** before deploying
✅ **Safe deployment** with automatic backups

### **Deployment is:**

- 🚀 **Fast** - One click or one command
- 🛡️ **Safe** - Automatic backups, easy rollback
- 📊 **Tracked** - Full deployment history
- 👁️ **Visible** - Clear UI and logging
- 🎯 **Professional** - Production-ready

---

## 🎯 **Next Steps**

### **After Reading This Guide:**

1. **✅ You already trained a model!** (Good job!)
2. **Deploy it now:**
   - Via UI: Learning Stats → Model Deployment → Deploy
   - Via CLI: `python deploy_model.py deploy best_model.pth`
3. **Test it** on a new document
4. **Compare** accuracy with baseline
5. **Decide** to keep or rollback

---

**Recommendation:** Use the UI for deployment. It's safer, more visual, and easier to use! 🎉

---

**Quick Deploy Right Now:**

```bash
# CLI way
python deploy_model.py deploy best_model.pth

# Or just go to:
# http://localhost:8000/canvas/{any_doc_id}
# → Learning Stats → Model Deployment → Click Deploy!
```

🚀 **Your trained model is ready to deploy!**


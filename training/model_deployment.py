"""
Model Deployment Manager
Handles deployment, rollback, and A/B testing of trained OCR models.
"""

import torch
from pathlib import Path
import json
import logging
import shutil
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class ModelDeploymentManager:
    """Manages OCR model deployment and versioning."""
    
    def __init__(
        self,
        models_dir: Path = Path("models/ocr_weights"),
        deployed_dir: Path = Path("models/deployed")
    ):
        self.models_dir = Path(models_dir)
        self.deployed_dir = Path(deployed_dir)
        self.deployed_dir.mkdir(parents=True, exist_ok=True)
        
        self.active_model_link = self.deployed_dir / "active_model.pth"
        self.deployment_history_file = self.deployed_dir / "deployment_history.json"
        
        logger.info(f"Deployment manager initialized")
        logger.info(f"Models directory: {self.models_dir}")
        logger.info(f"Deployed directory: {self.deployed_dir}")
    
    def list_available_models(self) -> List[Dict]:
        """List all trained models available for deployment."""
        models = []
        
        if not self.models_dir.exists():
            return models
        
        for model_file in self.models_dir.glob("*.pth"):
            try:
                # Load model metadata
                checkpoint = torch.load(model_file, map_location='cpu')
                
                # Get training report if available
                report_pattern = model_file.stem.replace("checkpoint_epoch_", "training_report_*")
                report_files = list(self.models_dir.glob(f"{report_pattern}.json"))
                
                model_info = {
                    "filename": model_file.name,
                    "path": str(model_file),
                    "epoch": checkpoint.get('epoch', 'unknown'),
                    "loss": float(checkpoint.get('loss', 0)),
                    "accuracy": float(checkpoint.get('accuracy', 0)),
                    "timestamp": checkpoint.get('timestamp', 'unknown'),
                    "vocab_size": len(checkpoint.get('vocab', [])),
                    "size_mb": model_file.stat().st_size / (1024 * 1024),
                    "is_best": "best" in model_file.stem,
                    "is_latest": "latest" in model_file.stem,
                    "has_report": len(report_files) > 0
                }
                
                models.append(model_info)
            except Exception as e:
                logger.warning(f"Could not read model {model_file}: {e}")
        
        # Sort by timestamp (newest first)
        models.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return models
    
    def get_active_model_info(self) -> Optional[Dict]:
        """Get information about the currently deployed model."""
        if not self.active_model_link.exists():
            return None
        
        try:
            checkpoint = torch.load(self.active_model_link, map_location='cpu')
            
            return {
                "path": str(self.active_model_link),
                "epoch": checkpoint.get('epoch', 'unknown'),
                "loss": float(checkpoint.get('loss', 0)),
                "accuracy": float(checkpoint.get('accuracy', 0)),
                "timestamp": checkpoint.get('timestamp', 'unknown'),
                "vocab_size": len(checkpoint.get('vocab', [])),
                "deployed_at": self._get_deployment_time()
            }
        except Exception as e:
            logger.error(f"Could not read active model: {e}")
            return None
    
    def _get_deployment_time(self) -> str:
        """Get the last deployment timestamp."""
        if not self.deployment_history_file.exists():
            return "unknown"
        
        try:
            with self.deployment_history_file.open('r') as f:
                history = json.load(f)
            
            if history and len(history) > 0:
                return history[-1].get('deployed_at', 'unknown')
        except:
            pass
        
        return "unknown"
    
    def deploy_model(
        self,
        model_filename: str,
        deployed_by: str = "system",
        notes: str = ""
    ) -> Dict:
        """
        Deploy a trained model to production.
        
        Args:
            model_filename: Name of the model file to deploy (e.g., "best_model.pth")
            deployed_by: User or system deploying the model
            notes: Optional deployment notes
        
        Returns:
            Deployment result dictionary
        """
        logger.info("=" * 60)
        logger.info("DEPLOYING OCR MODEL")
        logger.info("=" * 60)
        
        source_path = self.models_dir / model_filename
        
        if not source_path.exists():
            raise FileNotFoundError(f"Model not found: {source_path}")
        
        logger.info(f"Source model: {source_path}")
        logger.info(f"Deployed by: {deployed_by}")
        
        # Backup current active model if exists
        backup_path = None
        if self.active_model_link.exists():
            backup_path = self.deployed_dir / f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pth"
            shutil.copy2(self.active_model_link, backup_path)
            logger.info(f"✅ Backed up current model to: {backup_path}")
        
        # Copy new model to deployed directory
        deployed_path = self.deployed_dir / f"deployed_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pth"
        shutil.copy2(source_path, deployed_path)
        logger.info(f"✅ Copied model to: {deployed_path}")
        
        # Update active model link
        if self.active_model_link.exists():
            self.active_model_link.unlink()
        
        shutil.copy2(deployed_path, self.active_model_link)
        logger.info(f"✅ Updated active model link")
        
        # Load model info
        checkpoint = torch.load(source_path, map_location='cpu')
        
        # Record deployment in history
        deployment_record = {
            "deployed_at": datetime.utcnow().isoformat(),
            "source_model": model_filename,
            "deployed_path": str(deployed_path),
            "backup_path": str(backup_path) if backup_path else None,
            "deployed_by": deployed_by,
            "notes": notes,
            "model_info": {
                "epoch": checkpoint.get('epoch', 'unknown'),
                "loss": float(checkpoint.get('loss', 0)),
                "accuracy": float(checkpoint.get('accuracy', 0)),
                "vocab_size": len(checkpoint.get('vocab', []))
            }
        }
        
        self._add_to_deployment_history(deployment_record)
        
        logger.info("=" * 60)
        logger.info("✅ DEPLOYMENT COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info(f"Active model: {self.active_model_link}")
        logger.info(f"Backup saved: {backup_path}")
        logger.info(f"Model epoch: {deployment_record['model_info']['epoch']}")
        logger.info(f"Model accuracy: {deployment_record['model_info']['accuracy']:.2%}")
        
        return {
            "status": "success",
            "message": "Model deployed successfully",
            "deployment": deployment_record
        }
    
    def rollback_to_previous(self) -> Dict:
        """Rollback to the previous deployed model."""
        logger.info("ROLLING BACK TO PREVIOUS MODEL")
        
        history = self._load_deployment_history()
        
        if len(history) < 2:
            raise ValueError("No previous deployment found to rollback to")
        
        # Get previous deployment
        previous = history[-2]
        
        if not previous.get('backup_path'):
            raise ValueError("No backup available for previous deployment")
        
        backup_path = Path(previous['backup_path'])
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup model not found: {backup_path}")
        
        # Restore from backup
        if self.active_model_link.exists():
            self.active_model_link.unlink()
        
        shutil.copy2(backup_path, self.active_model_link)
        
        # Record rollback
        rollback_record = {
            "deployed_at": datetime.utcnow().isoformat(),
            "action": "rollback",
            "restored_from": str(backup_path),
            "previous_deployment": previous
        }
        
        self._add_to_deployment_history(rollback_record)
        
        logger.info(f"✅ Rolled back to: {backup_path}")
        
        return {
            "status": "success",
            "message": "Rolled back to previous model",
            "rollback": rollback_record
        }
    
    def get_deployment_history(self, limit: int = 10) -> List[Dict]:
        """Get deployment history."""
        history = self._load_deployment_history()
        return history[-limit:][::-1]  # Return last N, newest first
    
    def _load_deployment_history(self) -> List[Dict]:
        """Load deployment history from file."""
        if not self.deployment_history_file.exists():
            return []
        
        try:
            with self.deployment_history_file.open('r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load deployment history: {e}")
            return []
    
    def _add_to_deployment_history(self, record: Dict):
        """Add a record to deployment history."""
        history = self._load_deployment_history()
        history.append(record)
        
        with self.deployment_history_file.open('w') as f:
            json.dump(history, f, indent=2)
    
    def compare_models(self, model1_path: str, model2_path: str) -> Dict:
        """Compare two models."""
        def load_model_info(path):
            checkpoint = torch.load(Path(path), map_location='cpu')
            return {
                "epoch": checkpoint.get('epoch', 0),
                "loss": float(checkpoint.get('loss', 0)),
                "accuracy": float(checkpoint.get('accuracy', 0)),
                "vocab_size": len(checkpoint.get('vocab', []))
            }
        
        model1 = load_model_info(model1_path)
        model2 = load_model_info(model2_path)
        
        return {
            "model1": model1,
            "model2": model2,
            "comparison": {
                "accuracy_diff": model2['accuracy'] - model1['accuracy'],
                "loss_diff": model2['loss'] - model1['loss'],
                "better_model": "model2" if model2['accuracy'] > model1['accuracy'] else "model1"
            }
        }


def deploy_best_model(deployed_by: str = "system", notes: str = "") -> Dict:
    """
    Convenience function to deploy the best trained model.
    
    Args:
        deployed_by: User deploying the model
        notes: Deployment notes
    
    Returns:
        Deployment result
    """
    manager = ModelDeploymentManager()
    return manager.deploy_model("best_model.pth", deployed_by, notes)


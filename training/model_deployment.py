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


from database.connector import get_db
from database import models
from sqlalchemy.orm import Session

class ModelDeploymentManager:
    """Manages OCR model deployment and versioning using the database."""
    
    def __init__(
        self,
        db_session: Session,
        models_dir: Path = Path("models/ocr_weights"),
        deployed_dir: Path = Path("models/deployed")
    ):
        self.db = db_session
        self.models_dir = Path(models_dir)
        self.deployed_dir = Path(deployed_dir)
        self.deployed_dir.mkdir(parents=True, exist_ok=True)
        self.active_model_link = self.deployed_dir / "active_model.pth"

    def deploy_model(
        self,
        model_filename: str,
        deployed_by: str = "system",
        notes: str = ""
    ) -> Dict:
        """Deploys a model and records it in the database."""
        source_path = self.models_dir / model_filename
        if not source_path.exists():
            raise FileNotFoundError(f"Model not found: {source_path}")

        # Set previous model to inactive
        self.db.query(models.DeployedModel).filter(models.DeployedModel.is_active == True).update({models.DeployedModel.is_active: False})

        # Copy model file data into the database
        with open(source_path, 'rb') as f:
            model_data = f.read()

        # Create new deployment record
        new_deployment = models.DeployedModel(
            model_name=model_filename,
            model_data=model_data,
            is_active=True,
            accuracy=0.0 # Placeholder, should be read from training report
        )
        self.db.add(new_deployment)
        self.db.commit()

        # Physically write the active model file for the application to use
        with open(self.active_model_link, 'wb') as f:
            f.write(model_data)

        return {"status": "success", "message": f"Model {model_filename} deployed."}

    def get_active_model_info(self) -> Optional[Dict]:
        """Get information about the currently active model from the database."""
        active_model = self.db.query(models.DeployedModel).filter(models.DeployedModel.is_active == True).first()
        if not active_model:
            return None
        return {"model_name": active_model.model_name, "deployment_date": active_model.deployment_date.isoformat(), "accuracy": active_model.accuracy}

    def get_deployment_history(self, limit: int = 10) -> List[Dict]:
        """Get deployment history from the database."""
        history = self.db.query(models.DeployedModel).order_by(models.DeployedModel.deployment_date.desc()).limit(limit).all()
        return [{"model_name": h.model_name, "deployment_date": h.deployment_date.isoformat(), "is_active": h.is_active} for h in history]

    def rollback_to_previous(self) -> Dict:
        """Rollback to the previously active model in the database."""
        history = self.db.query(models.DeployedModel).order_by(models.DeployedModel.deployment_date.desc()).all()
        if len(history) < 2:
            raise ValueError("No previous deployment found to rollback to")
        
        current_active = history[0]
        previous_active = history[1]

        current_active.is_active = False
        previous_active.is_active = True
        self.db.commit()

        # Write the rolled-back model to the active file
        with open(self.active_model_link, 'wb') as f:
            f.write(previous_active.model_data)

        return {"status": "success", "message": f"Rolled back to model {previous_active.model_name}"}

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


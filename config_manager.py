"""
Configuration Manager for FinoktAI OCR System
Handles loading and managing system configuration settings
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages system configuration settings with defaults and validation."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file with fallback defaults."""
        default_config = {
            "lexicon_learning_threshold": 3,  # Default to 3 for safety
            "auto_correction_enabled": True,
            "document_types": {
                "invoice": {"lexicon_learning_threshold": 1, "auto_correction_enabled": True},
                "receipt": {"lexicon_learning_threshold": 1, "auto_correction_enabled": True},
                "identity_document": {"lexicon_learning_threshold": 1, "auto_correction_enabled": True},
                "contract": {"lexicon_learning_threshold": 1, "auto_correction_enabled": True},
                "bank_statement": {"lexicon_learning_threshold": 1, "auto_correction_enabled": True}
            },
            "ui_settings": {
                "show_autocorrection_indicators": True,
                "highlight_corrected_words": True,
                "show_correction_tooltips": True
            },
            "export_settings": {
                "include_correction_metadata": True,
                "use_corrected_text_only": True
            }
        }
        
        if not self.config_path.exists():
            logger.info(f"Config file {self.config_path} not found, creating with defaults")
            self._save_config(default_config)
            return default_config
        
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Merge with defaults to ensure all keys exist
            merged_config = self._merge_configs(default_config, config)
            
            # Validate configuration
            self._validate_config(merged_config)
            
            logger.info(f"Configuration loaded from {self.config_path}")
            return merged_config
            
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            logger.info("Using default configuration")
            return default_config
    
    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """Recursively merge loaded config with defaults."""
        result = default.copy()
        
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _validate_config(self, config: Dict) -> None:
        """Validate configuration values."""
        # Validate learning thresholds
        threshold = config.get("lexicon_learning_threshold", 3)
        if not isinstance(threshold, int) or threshold < 1:
            logger.warning(f"Invalid lexicon_learning_threshold: {threshold}, using default: 3")
            config["lexicon_learning_threshold"] = 3
        
        # Validate document type thresholds
        for doc_type, settings in config.get("document_types", {}).items():
            if "lexicon_learning_threshold" in settings:
                dt_threshold = settings["lexicon_learning_threshold"]
                if not isinstance(dt_threshold, int) or dt_threshold < 1:
                    logger.warning(f"Invalid threshold for {doc_type}: {dt_threshold}, using default: 1")
                    settings["lexicon_learning_threshold"] = 1
    
    def _save_config(self, config: Dict) -> None:
        """Save configuration to file."""
        try:
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_learning_threshold(self, document_type: Optional[str] = None) -> int:
        """Get learning threshold for document type or global default."""
        if document_type:
            type_threshold = self.get(f"document_types.{document_type}.lexicon_learning_threshold")
            if type_threshold is not None:
                return type_threshold
        
        return self.get("lexicon_learning_threshold", 3)
    
    def is_auto_correction_enabled(self, document_type: Optional[str] = None) -> bool:
        """Check if auto-correction is enabled for document type or globally."""
        if document_type:
            type_enabled = self.get(f"document_types.{document_type}.auto_correction_enabled")
            if type_enabled is not None:
                return type_enabled
        
        return self.get("auto_correction_enabled", True)
    
    def update(self, key: str, value: Any) -> None:
        """Update configuration value and save to file."""
        keys = key.split('.')
        config = self.config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        
        # Save to file
        self._save_config(self.config)
        logger.info(f"Updated config: {key} = {value}")
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self.config = self._load_config()
        logger.info("Configuration reloaded")

# Global configuration instance
_config_manager: Optional[ConfigManager] = None

def get_config() -> ConfigManager:
    """Get or create global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

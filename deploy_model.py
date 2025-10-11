#!/usr/bin/env python3
"""
Model Deployment CLI
Deploy trained OCR models from command line.
"""

import argparse
import logging
from pathlib import Path
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Deploy trained OCR models to production'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy a model')
    deploy_parser.add_argument(
        'model_filename',
        type=str,
        help='Model filename to deploy (e.g., best_model.pth)'
    )
    deploy_parser.add_argument(
        '--notes',
        type=str,
        default='',
        help='Deployment notes'
    )
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available models')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback to previous model')
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show deployment history')
    history_parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Number of history records to show'
    )
    
    # Active command
    active_parser = subparsers.add_parser('active', help='Show active model info')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        from training.model_deployment import ModelDeploymentManager
        
        manager = ModelDeploymentManager()
        
        if args.command == 'deploy':
            logger.info(f"Deploying model: {args.model_filename}")
            result = manager.deploy_model(
                args.model_filename,
                deployed_by='cli',
                notes=args.notes
            )
            logger.info("✅ Deployment successful!")
            logger.info(f"Active model: {manager.active_model_link}")
            
        elif args.command == 'list':
            models = manager.list_available_models()
            
            if not models:
                print("\nNo trained models found.")
                print("Train a model first: python train_model.py --epochs 20")
                return 0
            
            print(f"\n{'='*70}")
            print(f"AVAILABLE MODELS ({len(models)} total)")
            print(f"{'='*70}\n")
            
            for i, model in enumerate(models, 1):
                badge = " [BEST]" if model['is_best'] else " [LATEST]" if model['is_latest'] else ""
                print(f"{i}. {model['filename']}{badge}")
                print(f"   Epoch: {model['epoch']}")
                print(f"   Loss: {model['loss']:.4f}")
                print(f"   Accuracy: {model['accuracy']*100:.1f}%")
                print(f"   Size: {model['size_mb']:.2f} MB")
                print(f"   Created: {model['timestamp']}")
                print()
            
        elif args.command == 'rollback':
            logger.info("Rolling back to previous model...")
            result = manager.rollback_to_previous()
            logger.info("✅ Rollback successful!")
            
        elif args.command == 'history':
            history = manager.get_deployment_history(args.limit)
            
            if not history:
                print("\nNo deployment history found.")
                return 0
            
            print(f"\n{'='*70}")
            print(f"DEPLOYMENT HISTORY (last {len(history)} records)")
            print(f"{'='*70}\n")
            
            for i, record in enumerate(history, 1):
                action = record.get('action', 'deployment')
                model = record.get('source_model', 'Unknown')
                timestamp = record.get('deployed_at', 'Unknown')
                
                print(f"{i}. {action.upper()}: {model}")
                print(f"   Time: {timestamp}")
                if record.get('model_info'):
                    info = record['model_info']
                    print(f"   Epoch: {info.get('epoch', 'N/A')}")
                    print(f"   Accuracy: {info.get('accuracy', 0)*100:.1f}%")
                print()
            
        elif args.command == 'active':
            active = manager.get_active_model_info()
            
            if not active:
                print("\nNo model currently deployed.")
                print("Deploy a model: python deploy_model.py deploy best_model.pth")
                return 0
            
            print(f"\n{'='*70}")
            print("ACTIVE MODEL")
            print(f"{'='*70}\n")
            print(f"Path: {active['path']}")
            print(f"Epoch: {active['epoch']}")
            print(f"Loss: {active['loss']:.4f}")
            print(f"Accuracy: {active['accuracy']*100:.1f}%")
            print(f"Vocabulary size: {active['vocab_size']}")
            print(f"Deployed at: {active['deployed_at']}")
            print()
        
        return 0
        
    except ImportError as e:
        logger.error(f"❌ Deployment module not available: {e}")
        logger.error("Ensure training module is properly installed")
        return 1
        
    except Exception as e:
        logger.error(f"❌ Command failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())


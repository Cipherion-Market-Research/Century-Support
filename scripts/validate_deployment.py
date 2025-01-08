#!/usr/bin/env python3
import os
import sys
import json
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deployment-validator")

class DeploymentValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_file_structure(self) -> bool:
        """Validate required files and directories exist"""
        required_paths = [
            ("data/training/whitepaper.txt", "Whitepaper"),
            ("data/training/faq.json", "FAQ Data"),
            ("config/constants.py", "Constants"),
            ("core/message_handler.py", "Message Handler"),
            ("utils/logger.py", "Logger")
        ]
        
        for path, desc in required_paths:
            if not os.path.exists(path):
                self.errors.append(f"Missing {desc} at {path}")
        
        return len(self.errors) == 0

    def validate_python_syntax(self) -> bool:
        """Check Python files for syntax errors"""
        python_files = []
        for root, _, files in os.walk("."):
            for file in files:
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))

        for file_path in python_files:
            try:
                with open(file_path, 'r') as f:
                    compile(f.read(), file_path, 'exec')
            except SyntaxError as e:
                self.errors.append(f"Syntax error in {file_path}: {str(e)}")
                
        return len(self.errors) == 0

    def validate_json_files(self) -> bool:
        """Validate JSON files"""
        json_files = [
            "data/training/faq.json"
        ]
        
        for file_path in json_files:
            try:
                with open(file_path, 'r') as f:
                    json.load(f)
            except Exception as e:
                self.errors.append(f"Invalid JSON in {file_path}: {str(e)}")
                
        return len(self.errors) == 0

    def validate_imports(self) -> bool:
        """Validate Python imports"""
        try:
            import telegram
            import redis
            import aiohttp
            # Add other required packages
        except ImportError as e:
            self.errors.append(f"Missing dependency: {str(e)}")
            
        return len(self.errors) == 0

    def run_all_validations(self) -> bool:
        """Run all validation checks"""
        validations = [
            self.validate_file_structure,
            self.validate_python_syntax,
            self.validate_json_files,
            self.validate_imports
        ]
        
        all_passed = True
        for validation in validations:
            try:
                if not validation():
                    all_passed = False
            except Exception as e:
                self.errors.append(f"Validation error in {validation.__name__}: {str(e)}")
                all_passed = False
                
        return all_passed

def main():
    validator = DeploymentValidator()
    
    logger.info("Starting deployment validation...")
    
    if validator.run_all_validations():
        logger.info("✅ All validation checks passed!")
        if validator.warnings:
            logger.warning("⚠️ Warnings:")
            for warning in validator.warnings:
                logger.warning(f"- {warning}")
        sys.exit(0)
    else:
        logger.error("❌ Validation failed!")
        for error in validator.errors:
            logger.error(f"- {error}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
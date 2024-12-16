# utils/logger.py

import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

def setup_logger(name: str = __name__) -> logging.Logger:
    """Set up logger with rotating file handler"""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # Ensure DEBUG level

    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(
        f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log',
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )

    # Create formatters
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Add formatters to handlers
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

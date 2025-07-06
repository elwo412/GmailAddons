"""Logging configuration for Gmail GPT Categorizer."""

import sys
from typing import Optional

from loguru import logger


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Set up logging configuration using loguru.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    # Remove default logger to avoid duplicate logs
    logger.remove()
    
    # Console logging with colored output
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # File logging if specified
    if log_file:
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )
        
        logger.add(
            log_file,
            format=file_format,
            level=log_level,
            rotation="10 MB",  # Rotate when file reaches 10MB
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress rotated logs
            backtrace=True,
            diagnose=True
        )
        
        logger.info(f"Logging to file: {log_file}")
    
    # Set logging level for specific modules to reduce noise
    logger.disable("urllib3.connectionpool")  # Disable urllib3 debug logs
    logger.disable("google.auth.transport.requests")  # Disable Google auth debug logs
    
    logger.info(f"Logging initialized at level: {log_level}")


def get_logger(name: str):
    """Get a logger instance for a specific module."""
    return logger.bind(name=name) 
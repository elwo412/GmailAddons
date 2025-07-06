"""Gmail GPT Categorizer - Production-grade Gmail categorization using GPT."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .config import Config
from .gmail_client import GmailClient
from .gpt_categorizer import GPTCategorizer
from .models import EmailMessage, Category

__all__ = [
    "Config",
    "GmailClient", 
    "GPTCategorizer",
    "EmailMessage",
    "Category",
] 
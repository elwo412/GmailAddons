"""Configuration management for Gmail GPT Categorizer."""

import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration with environment variable support."""

    # Gmail API Configuration
    gmail_credentials_file: str = Field(
        default="credentials.json",
        description="Path to Gmail API credentials JSON file"
    )
    gmail_token_file: str = Field(
        default="token.json", 
        description="Path to store OAuth tokens"
    )
    gmail_scopes: List[str] = Field(
        default=["https://www.googleapis.com/auth/gmail.modify"],
        description="Gmail API scopes"
    )
    
    # OpenAI Configuration
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key for GPT integration"
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use for categorization"
    )
    openai_max_tokens: int = Field(
        default=150,
        description="Maximum tokens for GPT response"
    )
    openai_temperature: float = Field(
        default=0.3,
        description="Temperature for GPT responses"
    )
    
    # Gmail Processing Configuration
    max_messages_per_batch: int = Field(
        default=50,
        description="Maximum messages to process in one batch"
    )
    gmail_query: str = Field(
        default="in:inbox",
        description="Gmail query filter for fetching messages"
    )
    
    # Categories Configuration
    categories: List[str] = Field(
        default=[
            "Work", "Personal", "Finance", "Shopping", 
            "Newsletter", "Social", "Spam", "Other"
        ],
        description="Available categories for email classification"
    )
    
    # Pub/Sub Configuration (Optional)
    google_cloud_project_id: Optional[str] = Field(
        default=None,
        description="Google Cloud Project ID for Pub/Sub"
    )
    pubsub_topic_name: Optional[str] = Field(
        default=None,
        description="Pub/Sub topic name for Gmail push notifications"
    )
    pubsub_subscription_name: Optional[str] = Field(
        default=None,
        description="Pub/Sub subscription name"
    )
    
    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_file: Optional[str] = Field(
        default=None,
        description="Log file path (optional, logs to console if not set)"
    )
    
    # Application Configuration
    app_name: str = Field(
        default="Gmail GPT Categorizer",
        description="Application name"
    )
    app_version: str = Field(
        default="0.1.0",
        description="Application version"
    )
    
    @validator("gmail_credentials_file", "gmail_token_file")
    def validate_file_paths(cls, v: str) -> str:
        """Ensure file paths are absolute or relative to project root."""
        if not os.path.isabs(v):
            # Make relative to project root
            project_root = Path(__file__).parent.parent.parent
            v = str(project_root / v)
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @validator("openai_temperature")
    def validate_temperature(cls, v: float) -> float:
        """Validate OpenAI temperature parameter."""
        if not 0 <= v <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = "GMAIL_GPT_"


def get_config() -> Config:
    """Get application configuration instance."""
    return Config() 
"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from gmail_categorizer.config import Config, get_config


class TestConfig:
    """Test cases for Config class."""
    
    def test_config_with_required_fields(self):
        """Test config creation with required fields."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.openai_api_key == "test-key"
            assert config.openai_model == "gpt-4"  # default value
    
    def test_config_missing_required_field(self):
        """Test config fails without required OpenAI API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Config()
            assert "openai_api_key" in str(exc_info.value)
    
    def test_config_custom_values(self):
        """Test config with custom environment variables."""
        env_vars = {
            "GMAIL_GPT_OPENAI_API_KEY": "custom-key",
            "GMAIL_GPT_OPENAI_MODEL": "gpt-3.5-turbo",
            "GMAIL_GPT_OPENAI_TEMPERATURE": "0.7",
            "GMAIL_GPT_MAX_MESSAGES_PER_BATCH": "100",
            "GMAIL_GPT_LOG_LEVEL": "DEBUG"
        }
        
        with patch.dict(os.environ, env_vars):
            config = Config()
            assert config.openai_api_key == "custom-key"
            assert config.openai_model == "gpt-3.5-turbo"
            assert config.openai_temperature == 0.7
            assert config.max_messages_per_batch == 100
            assert config.log_level == "DEBUG"
    
    def test_config_invalid_log_level(self):
        """Test config validation for invalid log level."""
        with patch.dict(os.environ, {
            "GMAIL_GPT_OPENAI_API_KEY": "test-key",
            "GMAIL_GPT_LOG_LEVEL": "INVALID"
        }):
            with pytest.raises(ValidationError) as exc_info:
                Config()
            assert "Log level must be one of" in str(exc_info.value)
    
    def test_config_invalid_temperature(self):
        """Test config validation for invalid temperature."""
        with patch.dict(os.environ, {
            "GMAIL_GPT_OPENAI_API_KEY": "test-key",
            "GMAIL_GPT_OPENAI_TEMPERATURE": "3.0"
        }):
            with pytest.raises(ValidationError) as exc_info:
                Config()
            assert "Temperature must be between 0 and 2" in str(exc_info.value)
    
    def test_config_file_path_validation(self):
        """Test file path validation and conversion to absolute paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {
                "GMAIL_GPT_OPENAI_API_KEY": "test-key",
                "GMAIL_GPT_GMAIL_CREDENTIALS_FILE": "test_credentials.json",
                "GMAIL_GPT_GMAIL_TOKEN_FILE": "test_token.json"
            }):
                config = Config()
                
                # Should convert relative paths to absolute
                assert os.path.isabs(config.gmail_credentials_file)
                assert os.path.isabs(config.gmail_token_file)
                assert config.gmail_credentials_file.endswith("test_credentials.json")
                assert config.gmail_token_file.endswith("test_token.json")
    
    def test_config_categories_list(self):
        """Test categories configuration."""
        custom_categories = ["Work", "Personal", "Custom"]
        
        with patch.dict(os.environ, {
            "GMAIL_GPT_OPENAI_API_KEY": "test-key",
            "GMAIL_GPT_CATEGORIES": str(custom_categories)
        }):
            config = Config()
            assert config.categories == custom_categories
    
    def test_config_pubsub_settings(self):
        """Test Pub/Sub configuration settings."""
        with patch.dict(os.environ, {
            "GMAIL_GPT_OPENAI_API_KEY": "test-key",
            "GMAIL_GPT_GOOGLE_CLOUD_PROJECT_ID": "test-project",
            "GMAIL_GPT_PUBSUB_TOPIC_NAME": "test-topic",
            "GMAIL_GPT_PUBSUB_SUBSCRIPTION_NAME": "test-subscription"
        }):
            config = Config()
            assert config.google_cloud_project_id == "test-project"
            assert config.pubsub_topic_name == "test-topic"
            assert config.pubsub_subscription_name == "test-subscription"
    
    def test_get_config_function(self):
        """Test the get_config convenience function."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = get_config()
            assert isinstance(config, Config)
            assert config.openai_api_key == "test-key"


class TestConfigDefaults:
    """Test default configuration values."""
    
    def test_default_gmail_settings(self):
        """Test default Gmail settings."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.gmail_credentials_file.endswith("credentials.json")
            assert config.gmail_token_file.endswith("token.json")
            assert "https://www.googleapis.com/auth/gmail.modify" in config.gmail_scopes
            assert config.gmail_query == "in:inbox"
    
    def test_default_openai_settings(self):
        """Test default OpenAI settings."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.openai_model == "gpt-4"
            assert config.openai_max_tokens == 150
            assert config.openai_temperature == 0.3
    
    def test_default_processing_settings(self):
        """Test default processing settings."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.max_messages_per_batch == 50
            assert "Work" in config.categories
            assert "Personal" in config.categories
            assert "Other" in config.categories
    
    def test_default_logging_settings(self):
        """Test default logging settings."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.log_level == "INFO"
            assert config.log_file is None
    
    def test_default_app_settings(self):
        """Test default application settings."""
        with patch.dict(os.environ, {"GMAIL_GPT_OPENAI_API_KEY": "test-key"}):
            config = Config()
            assert config.app_name == "Gmail GPT Categorizer"
            assert config.app_version == "0.1.0" 
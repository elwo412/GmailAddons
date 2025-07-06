# Gmail GPT Categorizer

A production-grade Python application that automatically categorizes Gmail messages using OpenAI's GPT models and applies labels through the Gmail REST API.

## Features

- **Full Gmail API Integration**: OAuth 2.0 authentication with read/modify permissions
- **GPT-Powered Categorization**: Uses OpenAI models to intelligently categorize emails
- **Automatic Label Management**: Creates and applies Gmail labels based on categories
- **Real-time Push Notifications**: Optional Pub/Sub integration for immediate processing
- **Batch Processing**: Efficiently process multiple emails with rate limiting
- **Production Ready**: Comprehensive logging, error handling, and retry logic
- **CLI Interface**: Easy-to-use command-line interface with multiple commands
- **Configurable**: Environment-based configuration with validation

## Installation

### Prerequisites

- Python 3.8 or higher
- Gmail account with API access enabled
- OpenAI API key
- (Optional) Google Cloud Project for Pub/Sub notifications

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd GmailAddons
   ```

2. **Install the package**:
   ```bash
   # For production use
   pip install -e .
   
   # For development
   pip install -e ".[dev]"
   
   # For Pub/Sub functionality
   pip install -e ".[pubsub]"
   ```

3. **Set up Gmail API credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Gmail API
   - Create credentials (OAuth 2.0 Client ID)
   - Download the credentials file as `credentials.json` in the project root

4. **Configure environment variables**:
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env with your configuration
   nano .env
   ```

5. **Set required environment variables**:
   ```bash
   export GMAIL_GPT_OPENAI_API_KEY=your_openai_api_key
   # ... other variables as needed
   ```

## Configuration

The application uses environment variables with the prefix `GMAIL_GPT_`. Key configurations:

### Required Settings

- `GMAIL_GPT_OPENAI_API_KEY`: Your OpenAI API key

### Gmail Settings

- `GMAIL_GPT_GMAIL_CREDENTIALS_FILE`: Path to Gmail credentials JSON (default: `credentials.json`)
- `GMAIL_GPT_GMAIL_TOKEN_FILE`: Path to store OAuth tokens (default: `token.json`)
- `GMAIL_GPT_GMAIL_SCOPES`: Gmail API scopes (default: `["https://www.googleapis.com/auth/gmail.modify"]`)

### Processing Settings

- `GMAIL_GPT_MAX_MESSAGES_PER_BATCH`: Messages per batch (default: 50)
- `GMAIL_GPT_GMAIL_QUERY`: Gmail search query (default: `in:inbox`)
- `GMAIL_GPT_CATEGORIES`: Available categories as JSON array

### OpenAI Settings

- `GMAIL_GPT_OPENAI_MODEL`: Model to use (default: `gpt-4o-mini`)
- `GMAIL_GPT_OPENAI_MAX_TOKENS`: Max response tokens (default: 150)
- `GMAIL_GPT_OPENAI_TEMPERATURE`: Temperature setting (default: 0.3)

## Usage

### Command Line Interface

The application provides a comprehensive CLI with multiple commands:

#### Validate Setup

Test your configuration and API connections:

```bash
gmail-categorizer validate
```

#### Process Emails

Categorize and label emails:

```bash
# Process inbox emails with default settings
gmail-categorizer process

# Process specific query
gmail-categorizer process --query "in:inbox is:unread"

# Limit number of messages
gmail-categorizer process --max-messages 20

# Dry run (don't apply labels)
gmail-categorizer process --no-apply-labels

# Save results to file
gmail-categorizer process --output results.json
```

#### View Statistics

Get Gmail statistics and label information:

```bash
gmail-categorizer stats
gmail-categorizer stats --query "in:inbox from:example.com"
```

#### Manage Pub/Sub Notifications

Set up real-time email notifications:

```bash
# Set up push notifications
gmail-categorizer pubsub --setup

# Stop push notifications
gmail-categorizer pubsub --stop
```

#### Configuration Info

View current configuration:

```bash
gmail-categorizer config-info
```

### Python API

You can also use the components programmatically:

```python
from gmail_categorizer import Config, EmailProcessor

# Load configuration
config = Config()

# Initialize processor
processor = EmailProcessor(config)

# Validate setup
if processor.validate_setup():
    # Process emails
    result = processor.process_emails(
        query="in:inbox",
        max_messages=10,
        apply_labels=True
    )
    
    print(f"Processed {result.total_messages} emails")
    print(f"Success rate: {result.successful_categorizations}/{result.total_messages}")
```

## Architecture

The application follows a modular, production-ready architecture:

```
src/gmail_categorizer/
├── __init__.py          # Package initialization
├── config.py            # Configuration management
├── models.py            # Data models (Pydantic)
├── gmail_client.py      # Gmail API client
├── gpt_categorizer.py   # OpenAI integration
├── processor.py         # Main orchestrator
├── cli.py              # Command-line interface
└── logging_config.py   # Logging setup
```

### Key Components

- **Config**: Environment-based configuration with validation
- **GmailClient**: Gmail API wrapper with OAuth and retry logic
- **GPTCategorizer**: OpenAI integration for email categorization
- **EmailProcessor**: Main orchestrator coordinating all components
- **CLI**: Click-based command-line interface

### Data Models

All data structures use Pydantic for validation:

- `EmailMessage`: Parsed Gmail message
- `Category`: Classification result with confidence
- `CategorizationResult`: Single email processing result
- `BatchProcessingResult`: Batch processing summary
- `ProcessingStats`: Detailed processing statistics

## Categories

Default email categories:

- **Work**: Professional emails, meetings, work-related communications
- **Personal**: Personal emails from friends, family
- **Finance**: Banking, investments, financial services
- **Shopping**: E-commerce, receipts, order confirmations
- **Newsletter**: Newsletters, marketing emails, subscriptions
- **Social**: Social media notifications, community updates
- **Spam**: Unwanted emails, suspicious content
- **Other**: Emails that don't fit other categories

You can customize categories via the `GMAIL_GPT_CATEGORIES` environment variable.

## Gmail API Flow

The application follows this typical flow:

1. **OAuth Authentication**: Authenticate with Gmail using OAuth 2.0
2. **Message Discovery**: Use `GET /gmail/v1/users/me/messages` to find emails
3. **Message Retrieval**: Fetch full message content with `users.messages.get`
4. **GPT Categorization**: Send email content to OpenAI for classification
5. **Label Management**: Create labels with `users.labels.create` if needed
6. **Label Application**: Apply category labels with `users.threads.modify`
7. **Optional Pub/Sub**: Set up real-time notifications with `users.watch`

## Logging

The application uses structured logging with loguru:

- **Console Output**: Colored, formatted logs for development
- **File Logging**: Detailed logs with rotation and compression
- **Log Levels**: Configurable verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)

Log configuration:

```bash
# Set log level
export GMAIL_GPT_LOG_LEVEL=DEBUG

# Enable file logging
export GMAIL_GPT_LOG_FILE=logs/gmail_categorizer.log
```

## Error Handling

Comprehensive error handling includes:

- **Retry Logic**: Exponential backoff for API calls
- **Rate Limiting**: Respect Gmail and OpenAI rate limits
- **Graceful Degradation**: Continue processing on individual failures
- **Detailed Errors**: Structured error reporting and logging

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_gmail_client.py
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## Security

- **OAuth 2.0**: Secure Gmail authentication
- **Environment Variables**: Secrets stored in environment, not code
- **Token Storage**: Secure local token storage with refresh capability
- **Scope Minimization**: Only request necessary Gmail permissions

## Rate Limits

The application respects API rate limits:

- **Gmail API**: 1 billion quota units per day, with per-user limits
- **OpenAI API**: Varies by model and subscription tier
- **Built-in Retry Logic**: Automatic retry with exponential backoff

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   ```bash
   # Re-authenticate
   rm token.json
   gmail-categorizer validate
   ```

2. **API Quota Exceeded**:
   - Check your Google Cloud Console quotas
   - Reduce batch size with `--max-messages`

3. **OpenAI Rate Limits**:
   - Verify your OpenAI API key and billing
   - Check rate limits in OpenAI dashboard

4. **Permission Errors**:
   - Ensure Gmail API is enabled
   - Check OAuth scopes in configuration

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
gmail-categorizer --log-level DEBUG process
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run quality checks
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

1. Check the troubleshooting section
2. Search existing GitHub issues
3. Create a new issue with:
   - Error messages (without sensitive data)
   - Configuration (sanitized)
   - Steps to reproduce
   - Environment details 
"""Command-line interface for Gmail GPT Categorizer."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
from loguru import logger

from .config import get_config, Config
from .processor import EmailProcessor
from .logging_config import setup_logging


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set logging level"
)
@click.option(
    "--log-file",
    type=click.Path(),
    help="Log file path (optional, logs to console if not set)"
)
@click.pass_context
def cli(ctx, log_level: str, log_file: Optional[str]):
    """Gmail GPT Categorizer - Automatically categorize emails using AI."""
    ctx.ensure_object(dict)
    
    # Set up logging
    setup_logging(log_level, log_file)
    
    # Load configuration
    try:
        config = get_config()
        # Override log settings from CLI
        if log_level:
            config.log_level = log_level
        if log_file:
            config.log_file = log_file
        
        ctx.obj['config'] = config
        logger.info(f"Gmail GPT Categorizer v{config.app_version} initialized")
        
    except Exception as error:
        logger.error(f"Failed to load configuration: {error}")
        sys.exit(1)


@cli.command()
@click.option(
    "--query",
    default=None,
    help="Gmail search query (e.g., 'in:inbox is:unread')"
)
@click.option(
    "--max-messages",
    type=int,
    default=None,
    help="Maximum number of messages to process"
)
@click.option(
    "--no-apply-labels",
    is_flag=True,
    help="Skip applying labels to emails (dry run)"
)
@click.option(
    "--output",
    type=click.Path(),
    help="Save results to JSON file"
)
@click.option(
    "--concurrent",
    is_flag=True,
    help="Use concurrent processing for faster categorization"
)
@click.option(
    "--max-concurrent",
    type=int,
    default=5,
    help="Maximum number of concurrent API calls (default: 5)"
)
@click.pass_context
def process(ctx, query: Optional[str], max_messages: Optional[int], no_apply_labels: bool, output: Optional[str], concurrent: bool, max_concurrent: int):
    """Process and categorize emails."""
    config: Config = ctx.obj['config']
    
    try:
        # Initialize processor
        logger.info("Initializing email processor...")
        processor = EmailProcessor(config)
        
        # Process emails
        apply_labels = not no_apply_labels
        
        if concurrent:
            # Validate max_concurrent parameter
            if max_concurrent < 1:
                click.echo("Error: --max-concurrent must be at least 1", err=True)
                sys.exit(1)
            if max_concurrent > 20:
                click.echo("Warning: High concurrency (>20) may hit rate limits", err=True)
            
            click.echo(f"Using concurrent processing (max_concurrent={max_concurrent})")
            result = asyncio.run(processor.process_emails_concurrent(
                query=query,
                max_messages=max_messages,
                apply_labels=apply_labels,
                max_concurrent=max_concurrent
            ))
        else:
            click.echo("Using sequential processing")
            result = processor.process_emails(
                query=query,
                max_messages=max_messages,
                apply_labels=apply_labels
            )
        
        # Display results
        click.echo("\n" + "="*60)
        click.echo("PROCESSING RESULTS")
        click.echo("="*60)
        click.echo(f"Total messages processed: {result.total_messages}")
        click.echo(f"Successful categorizations: {result.successful_categorizations}")
        click.echo(f"Failed categorizations: {result.failed_categorizations}")
        click.echo(f"Processing time: {result.processing_time:.2f} seconds")
        
        # Show performance metrics
        if result.total_messages > 0:
            avg_time_per_email = result.processing_time / result.total_messages
            click.echo(f"Average time per email: {avg_time_per_email:.2f} seconds")
            
            if concurrent:
                # Estimate sequential time for comparison
                estimated_sequential_time = avg_time_per_email * result.total_messages
                if estimated_sequential_time > result.processing_time:
                    speedup = estimated_sequential_time / result.processing_time
                    click.echo(f"Estimated speedup: {speedup:.1f}x faster than sequential")
        
        if result.total_messages > 0:
            success_rate = (result.successful_categorizations / result.total_messages) * 100
            click.echo(f"Success rate: {success_rate:.1f}%")
        
        # Show category distribution
        if result.results:
            categories = [r.predicted_category for r in result.results if r.success]
            if categories:
                from collections import Counter
                category_counts = Counter(c.name for c in categories)
                
                click.echo("\nCategory Distribution:")
                for category, count in category_counts.most_common():
                    percentage = (count / len(categories)) * 100
                    click.echo(f"  {category}: {count} ({percentage:.1f}%)")
                
                # Average confidence
                avg_confidence = sum(c.confidence or 0 for c in categories) / len(categories)
                click.echo(f"\nAverage confidence: {avg_confidence:.3f}")
        
        # Show errors if any
        if result.errors:
            click.echo(f"\nErrors ({len(result.errors)}):")
            for error in result.errors[:5]:  # Show first 5 errors
                click.echo(f"  - {error}")
            if len(result.errors) > 5:
                click.echo(f"  ... and {len(result.errors) - 5} more")
        
        # Save results to file if requested
        if output:
            _save_results_to_file(result, output)
            click.echo(f"\nResults saved to: {output}")
        
        # Get processing stats
        stats = processor.get_processing_stats()
        click.echo(f"\nAPI Calls - Gmail: {stats.api_calls_gmail}, OpenAI: {stats.api_calls_openai}")
        
        if stats.categories_created > 0:
            click.echo(f"New labels created: {stats.categories_created}")
        
    except Exception as error:
        logger.error(f"Processing failed: {error}")
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate configuration and test connections."""
    config: Config = ctx.obj['config']
    
    try:
        click.echo("Validating Gmail GPT Categorizer setup...")
        
        # Initialize processor
        processor = EmailProcessor(config)
        
        # Run validation
        if processor.validate_setup():
            click.echo("✅ All validations passed!")
            click.echo("\nConfiguration Summary:")
            click.echo(f"  Gmail query: {config.gmail_query}")
            click.echo(f"  Max messages per batch: {config.max_messages_per_batch}")
            click.echo(f"  OpenAI model: {config.openai_model}")
            click.echo(f"  Categories ({len(config.categories)}): {', '.join(config.categories)}")
            
            if config.google_cloud_project_id:
                click.echo(f"  Pub/Sub project: {config.google_cloud_project_id}")
                if config.pubsub_topic_name:
                    click.echo(f"  Pub/Sub topic: {config.pubsub_topic_name}")
        else:
            click.echo("❌ Validation failed!")
            sys.exit(1)
            
    except Exception as error:
        logger.error(f"Validation failed: {error}")
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--query",
    default="in:inbox",
    help="Gmail search query to get stats for"
)
@click.pass_context
def stats(ctx, query: str):
    """Show Gmail statistics and label information."""
    config: Config = ctx.obj['config']
    
    try:
        click.echo("Fetching Gmail statistics...")
        
        # Initialize processor
        processor = EmailProcessor(config)
        
        # Get message count
        message_ids = processor.gmail_client.get_message_ids(query, 1000)  # Sample up to 1000
        click.echo(f"\nMessages matching '{query}': {len(message_ids)}")
        
        # Get labels
        labels = processor.gmail_client.get_labels()
        
        # Categorize labels
        user_labels = [l for l in labels if l.type == 'user']
        system_labels = [l for l in labels if l.type == 'system']
        category_labels = [l for l in user_labels if l.name in config.categories]
        
        click.echo(f"\nGmail Labels:")
        click.echo(f"  Total labels: {len(labels)}")
        click.echo(f"  User labels: {len(user_labels)}")
        click.echo(f"  System labels: {len(system_labels)}")
        click.echo(f"  Category labels: {len(category_labels)}")
        
        if category_labels:
            click.echo("\nExisting Category Labels:")
            for label in sorted(category_labels, key=lambda x: x.name):
                total = label.messages_total or 0
                unread = label.messages_unread or 0
                click.echo(f"  {label.name}: {total} total, {unread} unread")
        
        # Show configured categories not yet created as labels
        existing_category_names = {l.name for l in category_labels}
        missing_categories = set(config.categories) - existing_category_names
        
        if missing_categories:
            click.echo(f"\nCategories without labels: {', '.join(sorted(missing_categories))}")
        
    except Exception as error:
        logger.error(f"Stats collection failed: {error}")
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--setup",
    is_flag=True,
    help="Set up push notifications"
)
@click.option(
    "--stop",
    is_flag=True,
    help="Stop push notifications"
)
@click.pass_context
def pubsub(ctx, setup: bool, stop: bool):
    """Manage Gmail push notifications via Pub/Sub."""
    config: Config = ctx.obj['config']
    
    if not config.google_cloud_project_id:
        click.echo("Error: Google Cloud Project ID not configured", err=True)
        click.echo("Set GMAIL_GPT_GOOGLE_CLOUD_PROJECT_ID environment variable")
        sys.exit(1)
    
    if not config.pubsub_topic_name:
        click.echo("Error: Pub/Sub topic name not configured", err=True)
        click.echo("Set GMAIL_GPT_PUBSUB_TOPIC_NAME environment variable")
        sys.exit(1)
    
    try:
        processor = EmailProcessor(config)
        
        if setup:
            click.echo("Setting up Gmail push notifications...")
            if processor.setup_push_notifications():
                click.echo("✅ Push notifications set up successfully!")
            else:
                click.echo("❌ Failed to set up push notifications")
                sys.exit(1)
        
        elif stop:
            click.echo("Stopping Gmail push notifications...")
            if processor.stop_push_notifications():
                click.echo("✅ Push notifications stopped")
            else:
                click.echo("❌ Failed to stop push notifications")
                sys.exit(1)
        
        else:
            click.echo("Use --setup to enable or --stop to disable push notifications")
            click.echo(f"Project: {config.google_cloud_project_id}")
            click.echo(f"Topic: {config.pubsub_topic_name}")
    
    except Exception as error:
        logger.error(f"Pub/Sub operation failed: {error}")
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def config_info(ctx):
    """Show current configuration."""
    config: Config = ctx.obj['config']
    
    click.echo("Gmail GPT Categorizer Configuration")
    click.echo("="*40)
    
    # Gmail settings
    click.echo("\nGmail Settings:")
    click.echo(f"  Credentials file: {config.gmail_credentials_file}")
    click.echo(f"  Token file: {config.gmail_token_file}")
    click.echo(f"  Scopes: {', '.join(config.gmail_scopes)}")
    click.echo(f"  Query: {config.gmail_query}")
    click.echo(f"  Max messages per batch: {config.max_messages_per_batch}")
    
    # OpenAI settings
    click.echo("\nOpenAI Settings:")
    api_key_display = f"{config.openai_api_key[:8]}..." if config.openai_api_key else "Not set"
    click.echo(f"  API Key: {api_key_display}")
    click.echo(f"  Model: {config.openai_model}")
    click.echo(f"  Max tokens: {config.openai_max_tokens}")
    click.echo(f"  Temperature: {config.openai_temperature}")
    
    # Categories
    click.echo(f"\nCategories ({len(config.categories)}):")
    for i, category in enumerate(config.categories, 1):
        click.echo(f"  {i:2d}. {category}")
    
    # Pub/Sub settings
    click.echo("\nPub/Sub Settings:")
    click.echo(f"  Project ID: {config.google_cloud_project_id or 'Not set'}")
    click.echo(f"  Topic name: {config.pubsub_topic_name or 'Not set'}")
    click.echo(f"  Subscription: {config.pubsub_subscription_name or 'Not set'}")
    
    # Logging
    click.echo("\nLogging:")
    click.echo(f"  Level: {config.log_level}")
    click.echo(f"  File: {config.log_file or 'Console only'}")


def _save_results_to_file(result, output_path: str) -> None:
    """Save processing results to JSON file."""
    # Convert result to dict for JSON serialization
    result_dict = {
        "total_messages": result.total_messages,
        "successful_categorizations": result.successful_categorizations,
        "failed_categorizations": result.failed_categorizations,
        "processing_time": result.processing_time,
        "errors": result.errors,
        "results": []
    }
    
    for r in result.results:
        result_dict["results"].append({
            "message_id": r.message_id,
            "original_category": r.original_category,
            "predicted_category": {
                "name": r.predicted_category.name,
                "confidence": r.predicted_category.confidence,
                "reasoning": r.predicted_category.reasoning
            },
            "processing_time": r.processing_time,
            "success": r.success,
            "error_message": r.error_message
        })
    
    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(result_dict, f, indent=2)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main() 
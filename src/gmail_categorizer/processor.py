"""Main email processing orchestrator."""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger

from .config import Config
from .gmail_client import GmailClient
from .gpt_categorizer import GPTCategorizer
from .models import (
    EmailMessage, 
    Category, 
    CategorizationResult, 
    BatchProcessingResult,
    ProcessingStats,
    GmailLabel
)


class EmailProcessor:
    """Main email processing orchestrator."""
    
    def __init__(self, config: Config):
        """Initialize email processor with configuration."""
        self.config = config
        self.gmail_client = GmailClient(config)
        self.gpt_categorizer = GPTCategorizer(config)
        
        # Cache for Gmail labels
        self._label_cache: Dict[str, str] = {}  # category_name -> label_id
        self._label_lookup_cache: Dict[str, str] = {}  # label_id -> label_name
        self._stats = ProcessingStats(start_time=datetime.now())
        
        logger.info("Email processor initialized successfully")
    
    def process_emails(
        self, 
        query: Optional[str] = None,
        max_messages: Optional[int] = None,
        apply_labels: bool = True
    ) -> BatchProcessingResult:
        """
        Process emails: fetch, categorize, and optionally apply labels.
        
        Args:
            query: Gmail search query (uses config default if None)
            max_messages: Maximum messages to process (uses config default if None)
            apply_labels: Whether to apply category labels to emails
            
        Returns:
            BatchProcessingResult with processing summary
        """
        start_time = time.time()
        self._stats = ProcessingStats(start_time=datetime.now())
        
        query = query or self.config.gmail_query
        max_messages = max_messages or self.config.max_messages_per_batch
        
        logger.info(f"Starting email processing: query='{query}', max_messages={max_messages}")
        
        try:
            # Step 0: Build label caches for efficient lookup
            self._build_label_lookup_cache()
            
            # Step 1: Fetch message IDs
            logger.info("Fetching message IDs...")
            message_ids = self.gmail_client.get_message_ids(query, max_messages)
            self._stats.api_calls_gmail += 1
            
            if not message_ids:
                logger.info("No messages found matching query")
                return self._create_batch_result([], start_time)
            
            # Step 2: Fetch detailed message content
            logger.info(f"Fetching details for {len(message_ids)} messages...")
            emails = []
            for message_id in message_ids:
                try:
                    email = self.gmail_client.get_message(message_id)
                    emails.append(email)
                    self._stats.api_calls_gmail += 1
                except Exception as error:
                    logger.error(f"Failed to fetch message {message_id}: {error}")
                    self._stats.errors.append(f"Failed to fetch {message_id}: {str(error)}")
            
            self._stats.messages_processed = len(emails)
            logger.info(f"Successfully fetched {len(emails)} email messages")
            
            if not emails:
                logger.warning("No emails successfully fetched")
                return self._create_batch_result([], start_time)
            
            # Step 3: Categorize emails using GPT
            logger.info("Categorizing emails with GPT...")
            categorization_results = []
            
            for email in emails:
                result = self._categorize_single_email(email)
                categorization_results.append(result)
                
                if result.success:
                    self._stats.messages_categorized += 1
                else:
                    self._stats.messages_failed += 1
                    self._stats.errors.append(result.error_message or "Unknown error")
            
            # Step 4: Apply labels if requested
            if apply_labels:
                logger.info("Applying category labels to emails...")
                self._apply_labels_to_emails(categorization_results)
            
            # Step 5: Generate final results
            processing_time = time.time() - start_time
            self._stats.end_time = datetime.now()
            
            result = BatchProcessingResult(
                total_messages=len(emails),
                successful_categorizations=self._stats.messages_categorized,
                failed_categorizations=self._stats.messages_failed,
                processing_time=processing_time,
                results=categorization_results,
                errors=self._stats.errors
            )
            
            logger.info(
                f"Email processing completed in {processing_time:.2f}s: "
                f"{result.successful_categorizations}/{result.total_messages} successful"
            )
            
            return result
            
        except Exception as error:
            logger.error(f"Email processing failed: {error}")
            self._stats.errors.append(f"Processing failed: {str(error)}")
            self._stats.end_time = datetime.now()
            
            return BatchProcessingResult(
                total_messages=0,
                processing_time=time.time() - start_time,
                errors=[str(error)]
            )
    
    def _categorize_single_email(self, email: EmailMessage) -> CategorizationResult:
        """Categorize a single email and return result."""
        start_time = time.time()
        
        try:
            # Get original category if any
            original_category = self._get_current_category(email)
            
            # Categorize with GPT
            predicted_category = self.gpt_categorizer.categorize_email(email)
            self._stats.api_calls_openai += 1
            
            processing_time = time.time() - start_time
            
            return CategorizationResult(
                message_id=email.id,
                original_category=original_category,
                predicted_category=predicted_category,
                processing_time=processing_time,
                success=True
            )
            
        except Exception as error:
            processing_time = time.time() - start_time
            logger.error(f"Failed to categorize email {email.id}: {error}")
            
            return CategorizationResult(
                message_id=email.id,
                original_category=None,
                predicted_category=Category(name="Other", confidence=0.0),
                processing_time=processing_time,
                success=False,
                error_message=str(error)
            )
    
    def _get_current_category(self, email: EmailMessage) -> Optional[str]:
        """Extract current category from email labels using cached lookup."""
        if not email.labels:
            return None
        
        # Use cached label lookup instead of calling get_labels() for every email
        for label_id in email.labels:
            label_name = self._label_lookup_cache.get(label_id, "")
            if label_name in self.config.categories:
                return label_name
        
        return None
    
    def _apply_labels_to_emails(self, results: List[CategorizationResult]) -> None:
        """Apply category labels to emails based on categorization results."""
        # Build label cache if needed
        if not self._label_cache:
            self._build_label_cache()
        
        # Group results by category to minimize label creation calls
        category_groups = {}
        for result in results:
            if not result.success:
                continue
            
            # Skip if confidence is too low
            if result.predicted_category.confidence and result.predicted_category.confidence < 0.3:
                logger.debug(f"Skipping label application for {result.message_id} due to low confidence")
                continue
            
            category_name = result.predicted_category.name
            if category_name not in category_groups:
                category_groups[category_name] = []
            category_groups[category_name].append(result)
        
        # Process each category group
        for category_name, category_results in category_groups.items():
            # Get or create label once per category
            label_id = self._get_or_create_label(category_name)
            if not label_id:
                logger.warning(f"Could not get/create label for category: {category_name}")
                continue
            
            # Apply label to all messages in this category
            for result in category_results:
                success = self.gmail_client.add_label_to_message(result.message_id, label_id)
                if success:
                    logger.debug(f"Applied label '{category_name}' to message {result.message_id}")
                    self._stats.api_calls_gmail += 1
                else:
                    logger.warning(f"Failed to apply label to message {result.message_id}")
    
    def _build_label_lookup_cache(self) -> None:
        """Build cache for label ID to name lookup."""
        logger.debug("Building label lookup cache...")
        
        try:
            labels = self.gmail_client.get_labels()
            self._stats.api_calls_gmail += 1
            
            # Clear and rebuild lookup cache
            self._label_lookup_cache.clear()
            for label in labels:
                self._label_lookup_cache[label.id] = label.name
            
            logger.debug(f"Built label lookup cache with {len(self._label_lookup_cache)} labels")
            
        except Exception as error:
            logger.error(f"Failed to build label lookup cache: {error}")
    
    def _build_label_cache(self) -> None:
        """Build cache of category names to Gmail label IDs."""
        logger.debug("Building label cache...")
        
        try:
            labels = self.gmail_client.get_labels()
            self._stats.api_calls_gmail += 1
            
            # Clear and rebuild cache completely
            new_cache = {}
            for label in labels:
                # Check all configured categories plus any that might have been created
                if label.name in self.config.categories or label.type == 'user':
                    new_cache[label.name] = label.id
            
            # Update the cache
            self._label_cache.update(new_cache)
            
            logger.debug(f"Built label cache with {len(self._label_cache)} existing labels")
            
        except Exception as error:
            logger.error(f"Failed to build label cache: {error}")
    
    def _get_or_create_label(self, category_name: str) -> Optional[str]:
        """Get existing label ID or create new label for category."""
        # Check cache first
        if category_name in self._label_cache:
            return self._label_cache[category_name]
        
        # Refresh cache to check if label was created by another process
        self._build_label_cache()
        if category_name in self._label_cache:
            return self._label_cache[category_name]
        
        # Try to create new label
        try:
            label = self.gmail_client.create_label(
                name=category_name,
                description=f"Auto-generated label for {category_name} emails"
            )
            # Update both caches with the new label
            self._label_cache[category_name] = label.id
            self._label_lookup_cache[label.id] = label.name
            
            # Invalidate Gmail client cache so it refreshes on next call
            self.gmail_client._labels_cache = None
            
            self._stats.categories_created += 1
            self._stats.api_calls_gmail += 1
            
            logger.info(f"Created new label: {category_name}")
            return label.id
            
        except Exception as error:
            # Check if it's a "label already exists" error
            if "409" in str(error) or "exists" in str(error).lower():
                logger.info(f"Label {category_name} already exists, refreshing cache...")
                # Force refresh Gmail client cache and rebuild our caches
                self.gmail_client._labels_cache = None
                self._build_label_cache()
                if category_name in self._label_cache:
                    return self._label_cache[category_name]
            
            logger.error(f"Failed to create label for {category_name}: {error}")
            return None
    
    def _create_batch_result(
        self, 
        results: List[CategorizationResult], 
        start_time: float
    ) -> BatchProcessingResult:
        """Create BatchProcessingResult from categorization results."""
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        processing_time = time.time() - start_time
        
        return BatchProcessingResult(
            total_messages=len(results),
            successful_categorizations=successful,
            failed_categorizations=failed,
            processing_time=processing_time,
            results=results,
            errors=self._stats.errors
        )
    
    def get_processing_stats(self) -> ProcessingStats:
        """Get current processing statistics."""
        return self._stats
    
    def setup_push_notifications(self) -> bool:
        """Set up Gmail push notifications if configured."""
        if not self.config.pubsub_topic_name:
            logger.info("Pub/Sub topic not configured, skipping push notifications")
            return False
        
        return self.gmail_client.setup_push_notifications(self.config.pubsub_topic_name)
    
    def stop_push_notifications(self) -> bool:
        """Stop Gmail push notifications."""
        return self.gmail_client.stop_push_notifications()
    
    def validate_setup(self) -> bool:
        """Validate that all components are properly configured."""
        logger.info("Validating setup...")
        
        # Validate GPT categorizer
        if not self.gpt_categorizer.validate_categories():
            return False
        
        # Test Gmail connection
        try:
            self.gmail_client.get_labels()
            logger.info("Gmail connection validated")
        except Exception as error:
            logger.error(f"Gmail connection failed: {error}")
            return False
        
        # Test OpenAI connection
        try:
            # Create a simple test email
            test_email = EmailMessage(
                id="test",
                thread_id="test",
                subject="Test email",
                snippet="This is a test email for validation"
            )
            self.gpt_categorizer.categorize_email(test_email)
            logger.info("OpenAI connection validated")
        except Exception as error:
            logger.error(f"OpenAI connection failed: {error}")
            return False
        
        logger.info("Setup validation completed successfully")
        return True 
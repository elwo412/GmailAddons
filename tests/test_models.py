"""Tests for data models."""

from datetime import datetime
from typing import Dict, Any

import pytest
from pydantic import ValidationError

from gmail_categorizer.models import (
    EmailHeader,
    EmailMessage,
    Category,
    CategorizationResult,
    BatchProcessingResult,
    GmailLabel,
    ProcessingStats
)


class TestEmailMessage:
    """Test cases for EmailMessage model."""
    
    def test_email_message_minimal(self):
        """Test EmailMessage with minimal required fields."""
        message = EmailMessage(id="123", thread_id="456")
        assert message.id == "123"
        assert message.thread_id == "456"
        assert message.subject == ""
        assert message.labels == []
    
    def test_email_message_full(self):
        """Test EmailMessage with all fields."""
        headers = [
            EmailHeader(name="From", value="test@example.com"),
            EmailHeader(name="Subject", value="Test Subject")
        ]
        
        message = EmailMessage(
            id="123",
            thread_id="456",
            subject="Test Email",
            sender="test@example.com",
            recipient="recipient@example.com",
            date=datetime(2023, 1, 1, 12, 0, 0),
            body_text="This is a test email",
            body_html="<p>This is a test email</p>",
            snippet="This is a test...",
            labels=["INBOX", "UNREAD"],
            headers=headers,
            attachments=["document.pdf"]
        )
        
        assert message.subject == "Test Email"
        assert message.sender == "test@example.com"
        assert len(message.headers) == 2
        assert "document.pdf" in message.attachments
    
    def test_email_message_content_cleaning(self):
        """Test that email content is properly cleaned and truncated."""
        # Test with very long content
        long_content = "x" * 20000  # Longer than max_length
        
        message = EmailMessage(
            id="123",
            thread_id="456",
            body_text=long_content,
            body_html=long_content
        )
        
        # Should be truncated
        assert len(message.body_text) < len(long_content)
        assert message.body_text.endswith("...")
        assert len(message.body_html) < len(long_content)
        assert message.body_html.endswith("...")
    
    def test_get_content_for_categorization(self):
        """Test content extraction for GPT categorization."""
        message = EmailMessage(
            id="123",
            thread_id="456",
            subject="Meeting Tomorrow",
            sender="boss@company.com",
            body_text="Let's meet at 2 PM to discuss the project."
        )
        
        content = message.get_content_for_categorization()
        
        assert "Subject: Meeting Tomorrow" in content
        assert "From: boss@company.com" in content
        assert "Content: Let's meet at 2 PM" in content
    
    def test_get_content_for_categorization_long_body(self):
        """Test content extraction with long body text."""
        long_body = "This is a very long email body. " * 200  # Very long
        
        message = EmailMessage(
            id="123",
            thread_id="456",
            subject="Long Email",
            body_text=long_body
        )
        
        content = message.get_content_for_categorization()
        
        # Should be truncated
        assert "Subject: Long Email" in content
        assert len(content) < len(long_body)
        assert content.endswith("...")
    
    def test_get_content_fallback_to_snippet(self):
        """Test content extraction falls back to snippet when no body."""
        message = EmailMessage(
            id="123",
            thread_id="456",
            subject="No Body Email",
            snippet="This is the snippet text"
        )
        
        content = message.get_content_for_categorization()
        
        assert "Subject: No Body Email" in content
        assert "Content: This is the snippet text" in content


class TestCategory:
    """Test cases for Category model."""
    
    def test_category_basic(self):
        """Test basic Category creation."""
        category = Category(name="Work")
        assert category.name == "Work"
        assert category.label_id is None
        assert category.confidence is None
    
    def test_category_with_confidence(self):
        """Test Category with confidence score."""
        category = Category(
            name="Personal",
            confidence=0.85,
            reasoning="Email is from a family member"
        )
        assert category.name == "Personal"
        assert category.confidence == 0.85
        assert "family member" in category.reasoning
    
    def test_category_invalid_confidence(self):
        """Test Category validation for invalid confidence."""
        with pytest.raises(ValidationError) as exc_info:
            Category(name="Work", confidence=1.5)
        assert "Confidence must be between 0 and 1" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            Category(name="Work", confidence=-0.1)
        assert "Confidence must be between 0 and 1" in str(exc_info.value)


class TestCategorizationResult:
    """Test cases for CategorizationResult model."""
    
    def test_categorization_result_success(self):
        """Test successful categorization result."""
        category = Category(name="Work", confidence=0.9)
        result = CategorizationResult(
            message_id="123",
            predicted_category=category,
            processing_time=1.5,
            success=True
        )
        
        assert result.message_id == "123"
        assert result.predicted_category.name == "Work"
        assert result.processing_time == 1.5
        assert result.success is True
        assert result.error_message is None
    
    def test_categorization_result_failure(self):
        """Test failed categorization result."""
        category = Category(name="Other", confidence=0.0)
        result = CategorizationResult(
            message_id="123",
            predicted_category=category,
            processing_time=0.5,
            success=False,
            error_message="API timeout"
        )
        
        assert result.success is False
        assert result.error_message == "API timeout"


class TestBatchProcessingResult:
    """Test cases for BatchProcessingResult model."""
    
    def test_batch_processing_result(self):
        """Test batch processing result creation."""
        category = Category(name="Work", confidence=0.8)
        results = [
            CategorizationResult(
                message_id="123",
                predicted_category=category,
                processing_time=1.0,
                success=True
            )
        ]
        
        batch_result = BatchProcessingResult(
            total_messages=10,
            successful_categorizations=8,
            failed_categorizations=2,
            processing_time=15.5,
            results=results,
            errors=["Error 1", "Error 2"]
        )
        
        assert batch_result.total_messages == 10
        assert batch_result.successful_categorizations == 8
        assert batch_result.failed_categorizations == 2
        assert len(batch_result.results) == 1
        assert len(batch_result.errors) == 2


class TestProcessingStats:
    """Test cases for ProcessingStats model."""
    
    def test_processing_stats_basic(self):
        """Test basic ProcessingStats creation."""
        start_time = datetime(2023, 1, 1, 12, 0, 0)
        stats = ProcessingStats(start_time=start_time)
        
        assert stats.start_time == start_time
        assert stats.messages_processed == 0
        assert stats.messages_categorized == 0
        assert stats.errors == []
    
    def test_processing_stats_duration(self):
        """Test duration calculation."""
        start_time = datetime(2023, 1, 1, 12, 0, 0)
        end_time = datetime(2023, 1, 1, 12, 0, 30)  # 30 seconds later
        
        stats = ProcessingStats(
            start_time=start_time,
            end_time=end_time
        )
        
        assert stats.duration == 30.0
    
    def test_processing_stats_duration_none(self):
        """Test duration when end_time is None."""
        stats = ProcessingStats(start_time=datetime.now())
        assert stats.duration is None
    
    def test_processing_stats_success_rate(self):
        """Test success rate calculation."""
        stats = ProcessingStats(
            start_time=datetime.now(),
            messages_processed=100,
            messages_categorized=85
        )
        
        assert stats.success_rate == 85.0
    
    def test_processing_stats_success_rate_zero_messages(self):
        """Test success rate with zero messages."""
        stats = ProcessingStats(start_time=datetime.now())
        assert stats.success_rate == 0.0


class TestGmailLabel:
    """Test cases for GmailLabel model."""
    
    def test_gmail_label_basic(self):
        """Test basic GmailLabel creation."""
        label = GmailLabel(
            id="Label_123",
            name="Work",
            type="user"
        )
        
        assert label.id == "Label_123"
        assert label.name == "Work"
        assert label.type == "user"
        assert label.messages_total is None
    
    def test_gmail_label_with_counts(self):
        """Test GmailLabel with message counts."""
        label = GmailLabel(
            id="Label_456",
            name="INBOX",
            type="system",
            messages_total=150,
            messages_unread=25
        )
        
        assert label.messages_total == 150
        assert label.messages_unread == 25


class TestEmailHeader:
    """Test cases for EmailHeader model."""
    
    def test_email_header(self):
        """Test EmailHeader creation."""
        header = EmailHeader(name="Subject", value="Test Email")
        assert header.name == "Subject"
        assert header.value == "Test Email" 
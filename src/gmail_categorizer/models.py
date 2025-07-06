"""Data models for Gmail GPT Categorizer."""

from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, validator


class EmailHeader(BaseModel):
    """Email header information."""
    name: str
    value: str


class EmailMessage(BaseModel):
    """Gmail message model."""
    id: str = Field(..., description="Gmail message ID")
    thread_id: str = Field(..., description="Gmail thread ID")
    subject: str = Field(default="", description="Email subject")
    sender: str = Field(default="", description="Sender email address")
    recipient: str = Field(default="", description="Recipient email address")
    date: Optional[datetime] = Field(default=None, description="Email date")
    body_text: str = Field(default="", description="Plain text body")
    body_html: str = Field(default="", description="HTML body")
    snippet: str = Field(default="", description="Email snippet")
    labels: List[str] = Field(default_factory=list, description="Current Gmail labels")
    headers: List[EmailHeader] = Field(default_factory=list, description="Email headers")
    attachments: List[str] = Field(default_factory=list, description="Attachment filenames")
    raw_message: Optional[Dict[str, Any]] = Field(default=None, description="Raw Gmail API response")
    
    @validator("body_text", "body_html", pre=True)
    def clean_body_content(cls, v: str) -> str:
        """Clean and truncate body content."""
        if not v:
            return ""
        # Truncate very long content
        max_length = 10000
        if len(v) > max_length:
            v = v[:max_length] + "..."
        return v.strip()
    
    def get_content_for_categorization(self) -> str:
        """Get relevant content for GPT categorization."""
        content_parts = []
        
        if self.subject:
            content_parts.append(f"Subject: {self.subject}")
        
        if self.sender:
            content_parts.append(f"From: {self.sender}")
        
        # Prefer plain text, fall back to snippet
        body = self.body_text or self.snippet
        if body:
            # Limit body content for GPT
            max_body_length = 2000
            if len(body) > max_body_length:
                body = body[:max_body_length] + "..."
            content_parts.append(f"Content: {body}")
        
        return "\n".join(content_parts)


class Category(BaseModel):
    """Email category model."""
    name: str = Field(..., description="Category name")
    label_id: Optional[str] = Field(default=None, description="Gmail label ID")
    confidence: Optional[float] = Field(default=None, description="Categorization confidence")
    reasoning: Optional[str] = Field(default=None, description="GPT reasoning for categorization")
    
    @validator("confidence")
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        """Validate confidence score."""
        if v is not None and not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v


class CategorizationResult(BaseModel):
    """Result of email categorization."""
    message_id: str = Field(..., description="Gmail message ID")
    original_category: Optional[str] = Field(default=None, description="Original category if any")
    predicted_category: Category = Field(..., description="Predicted category")
    processing_time: float = Field(..., description="Processing time in seconds")
    success: bool = Field(default=True, description="Whether categorization was successful")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


class BatchProcessingResult(BaseModel):
    """Result of batch email processing."""
    total_messages: int = Field(..., description="Total messages processed")
    successful_categorizations: int = Field(default=0, description="Successful categorizations")
    failed_categorizations: int = Field(default=0, description="Failed categorizations")
    processing_time: float = Field(..., description="Total processing time in seconds")
    results: List[CategorizationResult] = Field(default_factory=list, description="Individual results")
    errors: List[str] = Field(default_factory=list, description="Processing errors")


class GmailLabel(BaseModel):
    """Gmail label model."""
    id: str = Field(..., description="Label ID")
    name: str = Field(..., description="Label name")
    type: str = Field(..., description="Label type (user or system)")
    messages_total: Optional[int] = Field(default=None, description="Total messages with this label")
    messages_unread: Optional[int] = Field(default=None, description="Unread messages with this label")


class PubSubMessage(BaseModel):
    """Pub/Sub notification message model."""
    message_id: str = Field(..., description="Pub/Sub message ID")
    publish_time: datetime = Field(..., description="Message publish time")
    history_id: str = Field(..., description="Gmail history ID")
    email_address: str = Field(..., description="Gmail address")


class ProcessingStats(BaseModel):
    """Processing statistics model."""
    start_time: datetime = Field(..., description="Processing start time")
    end_time: Optional[datetime] = Field(default=None, description="Processing end time")
    messages_processed: int = Field(default=0, description="Messages processed")
    messages_categorized: int = Field(default=0, description="Messages successfully categorized")
    messages_failed: int = Field(default=0, description="Messages that failed processing")
    categories_created: int = Field(default=0, description="New categories/labels created")
    api_calls_gmail: int = Field(default=0, description="Gmail API calls made")
    api_calls_openai: int = Field(default=0, description="OpenAI API calls made")
    errors: List[str] = Field(default_factory=list, description="Processing errors")
    
    @property
    def duration(self) -> Optional[float]:
        """Get processing duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success_rate(self) -> float:
        """Get success rate percentage."""
        if self.messages_processed == 0:
            return 0.0
        return (self.messages_categorized / self.messages_processed) * 100 
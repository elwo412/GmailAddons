"""Gmail API client with OAuth authentication and message management."""

import base64
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

import httplib2
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config
from .models import EmailMessage, EmailHeader, GmailLabel


class GmailClient:
    """Gmail API client with authentication and message management."""
    
    def __init__(self, config: Config):
        """Initialize Gmail client with configuration."""
        self.config = config
        self.service = None
        self.credentials = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth 2.0."""
        creds = None
        
        # Load existing token
        if os.path.exists(self.config.gmail_token_file):
            try:
                creds = Credentials.from_authorized_user_file(
                    self.config.gmail_token_file, 
                    self.config.gmail_scopes
                )
                logger.info("Loaded existing credentials from token file")
            except Exception as e:
                logger.warning(f"Failed to load existing credentials: {e}")
        
        # If there are no valid credentials, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Refreshed expired credentials")
                except Exception as e:
                    logger.warning(f"Failed to refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.config.gmail_credentials_file):
                    raise FileNotFoundError(
                        f"Gmail credentials file not found: {self.config.gmail_credentials_file}"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.config.gmail_credentials_file, 
                    self.config.gmail_scopes
                )
                creds = flow.run_local_server(port=0)
                logger.info("Completed OAuth flow with new credentials")
            
            # Save the credentials for the next run
            with open(self.config.gmail_token_file, 'w') as token:
                token.write(creds.to_json())
                logger.info(f"Saved credentials to {self.config.gmail_token_file}")
        
        self.credentials = creds
        self.service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail API client initialized successfully")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_message_ids(self, query: str = "in:inbox", max_results: int = 50) -> List[str]:
        """
        Get list of message IDs based on query.
        
        Args:
            query: Gmail search query (default: "in:inbox")
            max_results: Maximum number of messages to fetch
            
        Returns:
            List of message IDs
        """
        try:
            logger.info(f"Fetching message IDs with query: {query}, max_results: {max_results}")
            
            result = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = result.get('messages', [])
            message_ids = [msg['id'] for msg in messages]
            
            logger.info(f"Found {len(message_ids)} messages")
            return message_ids
            
        except HttpError as error:
            logger.error(f"Failed to fetch message IDs: {error}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_message(self, message_id: str) -> EmailMessage:
        """
        Get detailed message information.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            EmailMessage object with parsed content
        """
        try:
            logger.debug(f"Fetching message details for ID: {message_id}")
            
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            return self._parse_message(message)
            
        except HttpError as error:
            logger.error(f"Failed to fetch message {message_id}: {error}")
            raise
    
    def _parse_message(self, raw_message: Dict[str, Any]) -> EmailMessage:
        """Parse raw Gmail message into EmailMessage object."""
        payload = raw_message.get('payload', {})
        headers = payload.get('headers', [])
        
        # Extract headers
        subject = ""
        sender = ""
        recipient = ""
        date_str = ""
        
        for header in headers:
            name = header.get('name', '').lower()
            value = header.get('value', '')
            
            if name == 'subject':
                subject = value
            elif name == 'from':
                sender = value
            elif name == 'to':
                recipient = value
            elif name == 'date':
                date_str = value
        
        # Parse date
        message_date = None
        if date_str:
            try:
                # This is a simplified date parsing - you might want to use dateutil
                message_date = datetime.strptime(
                    date_str.split('(')[0].strip(), 
                    '%a, %d %b %Y %H:%M:%S %z'
                )
            except:
                logger.warning(f"Failed to parse date: {date_str}")
        
        # Extract body content
        body_text = ""
        body_html = ""
        attachments = []
        
        def extract_parts(parts):
            nonlocal body_text, body_html, attachments
            
            for part in parts:
                mime_type = part.get('mimeType', '')
                
                if mime_type == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                
                elif mime_type == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                
                elif 'multipart' in mime_type:
                    sub_parts = part.get('parts', [])
                    extract_parts(sub_parts)
                
                elif part.get('filename'):
                    attachments.append(part.get('filename'))
        
        # Handle different payload structures
        if 'parts' in payload:
            extract_parts(payload['parts'])
        else:
            # Single part message
            mime_type = payload.get('mimeType', '')
            if mime_type == 'text/plain':
                data = payload.get('body', {}).get('data', '')
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif mime_type == 'text/html':
                data = payload.get('body', {}).get('data', '')
                if data:
                    body_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        # Create EmailMessage object
        return EmailMessage(
            id=raw_message['id'],
            thread_id=raw_message['threadId'],
            subject=subject,
            sender=sender,
            recipient=recipient,
            date=message_date,
            body_text=body_text,
            body_html=body_html,
            snippet=raw_message.get('snippet', ''),
            labels=raw_message.get('labelIds', []),
            headers=[EmailHeader(name=h['name'], value=h['value']) for h in headers],
            attachments=attachments,
            raw_message=raw_message
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_labels(self) -> List[GmailLabel]:
        """Get all Gmail labels."""
        try:
            logger.debug("Fetching Gmail labels")
            
            result = self.service.users().labels().list(userId='me').execute()
            labels = result.get('labels', [])
            
            gmail_labels = []
            for label in labels:
                gmail_labels.append(GmailLabel(
                    id=label['id'],
                    name=label['name'],
                    type=label['type'],
                    messages_total=label.get('messagesTotal'),
                    messages_unread=label.get('messagesUnread')
                ))
            
            logger.info(f"Found {len(gmail_labels)} labels")
            return gmail_labels
            
        except HttpError as error:
            logger.error(f"Failed to fetch labels: {error}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def create_label(self, name: str, description: str = "") -> GmailLabel:
        """
        Create a new Gmail label.
        
        Args:
            name: Label name
            description: Label description
            
        Returns:
            Created GmailLabel object
        """
        try:
            logger.info(f"Creating label: {name}")
            
            label_object = {
                'name': name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            
            if description:
                label_object['description'] = description
            
            result = self.service.users().labels().create(
                userId='me',
                body=label_object
            ).execute()
            
            logger.info(f"Created label: {name} with ID: {result['id']}")
            
            return GmailLabel(
                id=result['id'],
                name=result['name'],
                type=result['type']
            )
            
        except HttpError as error:
            logger.error(f"Failed to create label {name}: {error}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def add_label_to_message(self, message_id: str, label_id: str) -> bool:
        """
        Add a label to a message.
        
        Args:
            message_id: Gmail message ID
            label_id: Gmail label ID
            
        Returns:
            True if successful
        """
        try:
            logger.debug(f"Adding label {label_id} to message {message_id}")
            
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            
            logger.debug(f"Successfully added label to message {message_id}")
            return True
            
        except HttpError as error:
            logger.error(f"Failed to add label to message {message_id}: {error}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def remove_label_from_message(self, message_id: str, label_id: str) -> bool:
        """
        Remove a label from a message.
        
        Args:
            message_id: Gmail message ID
            label_id: Gmail label ID
            
        Returns:
            True if successful
        """
        try:
            logger.debug(f"Removing label {label_id} from message {message_id}")
            
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': [label_id]}
            ).execute()
            
            logger.debug(f"Successfully removed label from message {message_id}")
            return True
            
        except HttpError as error:
            logger.error(f"Failed to remove label from message {message_id}: {error}")
            return False
    
    def setup_push_notifications(self, topic_name: str) -> bool:
        """
        Set up Gmail push notifications via Pub/Sub.
        
        Args:
            topic_name: Pub/Sub topic name
            
        Returns:
            True if successful
        """
        if not self.config.google_cloud_project_id:
            logger.warning("Google Cloud Project ID not configured for Pub/Sub")
            return False
        
        try:
            logger.info(f"Setting up push notifications for topic: {topic_name}")
            
            request = {
                'topicName': f"projects/{self.config.google_cloud_project_id}/topics/{topic_name}"
            }
            
            result = self.service.users().watch(
                userId='me',
                body=request
            ).execute()
            
            logger.info(f"Push notifications set up successfully. History ID: {result['historyId']}")
            return True
            
        except HttpError as error:
            logger.error(f"Failed to set up push notifications: {error}")
            return False
    
    def stop_push_notifications(self) -> bool:
        """Stop Gmail push notifications."""
        try:
            logger.info("Stopping push notifications")
            
            self.service.users().stop(userId='me').execute()
            
            logger.info("Push notifications stopped successfully")
            return True
            
        except HttpError as error:
            logger.error(f"Failed to stop push notifications: {error}")
            return False 
"""GPT-based email categorization using OpenAI API."""

import json
import re
import time
from typing import List, Optional, Dict, Any

import openai
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config
from .models import EmailMessage, Category


class GPTCategorizer:
    """GPT-based email categorizer using OpenAI API."""
    
    def __init__(self, config: Config):
        """Initialize GPT categorizer with configuration."""
        self.config = config
        self.client = openai.OpenAI(api_key=config.openai_api_key)
        self.categories = config.categories
        
        logger.info(f"GPT Categorizer initialized with model: {config.openai_model}")
        logger.info(f"Available categories: {', '.join(self.categories)}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for email categorization."""
        categories_list = ", ".join(self.categories)
        
        return f"""You are an expert email categorization assistant. Your task is to categorize emails into one of the following categories:

Categories: {categories_list}

Instructions:
1. Analyze the email subject, sender, and content
2. Choose the MOST appropriate category from the list above
3. Provide a confidence score between 0 and 1
4. Give a brief reasoning for your choice
5. Respond ONLY with a valid JSON object in this exact format:

{{
    "category": "CategoryName",
    "confidence": 0.85,
    "reasoning": "Brief explanation of why this category was chosen"
}}

Rules:
- Always use one of the provided categories exactly as listed
- Confidence should reflect how certain you are (0.0 to 1.0)
- Keep reasoning concise (1-2 sentences)
- If unsure, use "Other" category with lower confidence
- Focus on the primary purpose/content of the email"""
    
    def _build_user_prompt(self, email: EmailMessage) -> str:
        """Build user prompt with email content."""
        content = email.get_content_for_categorization()
        
        # Truncate if too long to avoid token limits
        max_content_length = 3000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        
        return f"""Please categorize this email:

{content}"""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def categorize_email(self, email: EmailMessage) -> Category:
        """
        Categorize a single email using GPT.
        
        Args:
            email: EmailMessage object to categorize
            
        Returns:
            Category object with prediction and confidence
        """
        start_time = time.time()
        
        try:
            logger.debug(f"Categorizing email: {email.id} - {email.subject[:50]}...")
            
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(email)
            
            # Try with JSON response format first, fall back if not supported
            try:
                response = self.client.chat.completions.create(
                    model=self.config.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=self.config.openai_max_tokens,
                    temperature=self.config.openai_temperature,
                    response_format={"type": "json_object"}
                )
            except Exception as json_error:
                if "response_format" in str(json_error):
                    logger.warning(f"Model {self.config.openai_model} doesn't support JSON format, using text mode")
                    response = self.client.chat.completions.create(
                        model=self.config.openai_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=self.config.openai_max_tokens,
                        temperature=self.config.openai_temperature
                    )
                else:
                    raise json_error
            
            # Parse response
            response_text = response.choices[0].message.content.strip()
            result = self._parse_gpt_response(response_text)
            
            processing_time = time.time() - start_time
            logger.debug(
                f"Categorized email {email.id} as '{result.name}' "
                f"(confidence: {result.confidence:.2f}) in {processing_time:.2f}s"
            )
            
            return result
            
        except Exception as error:
            processing_time = time.time() - start_time
            logger.error(f"Failed to categorize email {email.id}: {error}")
            
            # Return fallback category
            return Category(
                name="Other",
                confidence=0.0,
                reasoning=f"Categorization failed: {str(error)}"
            )
    
    def _parse_gpt_response(self, response_text: str) -> Category:
        """Parse GPT response and extract category information."""
        try:
            # Try to parse as JSON
            data = json.loads(response_text)
            
            category_name = data.get("category", "Other")
            confidence = data.get("confidence", 0.0)
            reasoning = data.get("reasoning", "No reasoning provided")
            
            # Validate category name
            if category_name not in self.categories:
                logger.warning(f"Invalid category '{category_name}', using 'Other'")
                category_name = "Other"
                confidence = max(0.0, confidence - 0.3)  # Reduce confidence
            
            # Validate confidence
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                logger.warning(f"Invalid confidence {confidence}, setting to 0.5")
                confidence = 0.5
            
            return Category(
                name=category_name,
                confidence=float(confidence),
                reasoning=str(reasoning)
            )
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON response: {response_text}")
            
            # Try to extract category from text using regex
            category_match = re.search(
                r'\b(' + '|'.join(re.escape(cat) for cat in self.categories) + r')\b',
                response_text,
                re.IGNORECASE
            )
            
            if category_match:
                category_name = category_match.group(1)
                # Find matching category with correct case
                for cat in self.categories:
                    if cat.lower() == category_name.lower():
                        category_name = cat
                        break
                
                return Category(
                    name=category_name,
                    confidence=0.3,  # Lower confidence for regex extraction
                    reasoning="Extracted from non-JSON response"
                )
            
            # Fallback
            return Category(
                name="Other",
                confidence=0.0,
                reasoning="Could not parse response"
            )
    
    async def categorize_emails_batch(self, emails: List[EmailMessage]) -> List[Category]:
        """
        Categorize multiple emails in batch.
        
        Args:
            emails: List of EmailMessage objects
            
        Returns:
            List of Category objects in same order as input
        """
        logger.info(f"Starting batch categorization of {len(emails)} emails")
        start_time = time.time()
        
        categories = []
        for i, email in enumerate(emails):
            try:
                category = self.categorize_email(email)
                categories.append(category)
                
                # Log progress
                if (i + 1) % 10 == 0:
                    logger.info(f"Processed {i + 1}/{len(emails)} emails")
                
            except Exception as error:
                logger.error(f"Failed to categorize email {email.id}: {error}")
                categories.append(Category(
                    name="Other",
                    confidence=0.0,
                    reasoning=f"Processing error: {str(error)}"
                ))
        
        total_time = time.time() - start_time
        logger.info(
            f"Batch categorization completed: {len(categories)} emails in {total_time:.2f}s "
            f"(avg: {total_time/len(emails):.2f}s per email)"
        )
        
        return categories
    
    def get_category_stats(self, categories: List[Category]) -> Dict[str, Any]:
        """
        Get statistics about categorization results.
        
        Args:
            categories: List of Category objects
            
        Returns:
            Dictionary with statistics
        """
        if not categories:
            return {}
        
        # Count by category
        category_counts = {}
        confidence_sum = 0
        confidence_count = 0
        
        for category in categories:
            category_counts[category.name] = category_counts.get(category.name, 0) + 1
            
            if category.confidence is not None:
                confidence_sum += category.confidence
                confidence_count += 1
        
        # Calculate statistics
        avg_confidence = confidence_sum / confidence_count if confidence_count > 0 else 0.0
        
        # Sort categories by count
        sorted_categories = sorted(
            category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            "total_emails": len(categories),
            "average_confidence": round(avg_confidence, 3),
            "category_distribution": dict(sorted_categories),
            "most_common_category": sorted_categories[0][0] if sorted_categories else None,
            "high_confidence_count": sum(
                1 for c in categories 
                if c.confidence and c.confidence >= 0.8
            ),
            "low_confidence_count": sum(
                1 for c in categories 
                if c.confidence and c.confidence < 0.5
            )
        }
    
    def validate_categories(self) -> bool:
        """Validate that configured categories are reasonable."""
        if not self.categories:
            logger.error("No categories configured")
            return False
        
        if len(self.categories) > 20:
            logger.warning("Large number of categories may reduce accuracy")
        
        # Check for duplicates
        unique_categories = set(self.categories)
        if len(unique_categories) != len(self.categories):
            logger.error("Duplicate categories found in configuration")
            return False
        
        logger.info(f"Category validation passed: {len(self.categories)} unique categories")
        return True 
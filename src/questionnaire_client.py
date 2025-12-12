"""Client for fetching questionnaire/protocol from API."""
import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class QuestionnaireClient:
    """Client to fetch questionnaire (protocol) from API by campaign_id."""
    
    def __init__(self, api_base_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize questionnaire client.
        
        Args:
            api_base_url: Base URL of the API (e.g., "https://api.example.com")
            api_key: API key for authentication (HIRING_API_TOKEN)
        """
        self.api_base_url = api_base_url or os.getenv("HIRINGS_API_URL", "").rstrip("/")
        self.api_key = api_key or os.getenv("HIRING_API_TOKEN")
        
        if not self.api_base_url:
            raise ValueError("HIRINGS_API_URL not configured")
        if not self.api_key:
            raise ValueError("HIRING_API_TOKEN not configured")
    
    async def get_questionnaire(self, campaign_id: str) -> Dict[str, Any]:
        """
        Fetch questionnaire/protocol by campaign_id.
        
        Args:
            campaign_id: Campaign ID (e.g., "255")
            
        Returns:
            Protocol/Questionnaire JSON structure
            
        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.api_base_url}/questionnaire/{campaign_id}"
        
        headers = {
            "Authorization": self.api_key,  # Direct token, no Bearer prefix
            "Content-Type": "application/json"
        }
        
        logger.info(f"Fetching questionnaire for campaign_id={campaign_id} from {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                questionnaire = response.json()
                logger.info(f"Successfully fetched questionnaire for campaign {campaign_id}")
                
                return questionnaire
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching questionnaire: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error fetching questionnaire: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error fetching questionnaire: {e}")
                raise
    
    def get_questionnaire_sync(self, campaign_id: str) -> Dict[str, Any]:
        """
        Synchronous version of get_questionnaire.
        
        Args:
            campaign_id: Campaign ID (e.g., "255")
            
        Returns:
            Protocol/Questionnaire JSON structure
        """
        url = f"{self.api_base_url}/questionnaire/{campaign_id}"
        
        headers = {
            "Authorization": self.api_key,  # Direct token, no Bearer prefix
            "Content-Type": "application/json"
        }
        
        logger.info(f"Fetching questionnaire for campaign_id={campaign_id} from {url}")
        
        with httpx.Client(timeout=30.0) as client:
            try:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                
                questionnaire = response.json()
                logger.info(f"Successfully fetched questionnaire for campaign {campaign_id}")
                
                return questionnaire
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching questionnaire: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error fetching questionnaire: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error fetching questionnaire: {e}")
                raise


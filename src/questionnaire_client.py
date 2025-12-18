"""Client for fetching transcript/protocol from HOC API."""
import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class QuestionnaireClient:
    """Client to fetch transcript (Gesprächsprotokoll) from HOC API by campaign_id."""
    
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
        Fetch transcript (Gesprächsprotokoll) by campaign_id.
        
        This fetches the EXISTING transcript with all metadata (created_on, updated_on, etc.),
        not just the questionnaire template.
        
        Args:
            campaign_id: Campaign ID (e.g., "255")
            
        Returns:
            Transcript/Protocol JSON structure with metadata
            
        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.api_base_url}/campaigns/{campaign_id}/transcript/"
        
        headers = {
            "Authorization": self.api_key,  # Direct token, no Bearer prefix
            "Content-Type": "application/json"
        }
        
        logger.info(f"Fetching transcript for campaign_id={campaign_id} from {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                transcript = response.json()
                logger.info(f"Successfully fetched transcript for campaign {campaign_id}")
                
                return transcript
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching transcript: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error fetching transcript: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error fetching transcript: {e}")
                raise
    
    def get_questionnaire_sync(self, campaign_id: str) -> Dict[str, Any]:
        """
        Synchronous version of get_questionnaire.
        
        Args:
            campaign_id: Campaign ID (e.g., "255")
            
        Returns:
            Transcript/Protocol JSON structure with metadata
        """
        url = f"{self.api_base_url}/campaigns/{campaign_id}/transcript/"
        
        headers = {
            "Authorization": self.api_key,  # Direct token, no Bearer prefix
            "Content-Type": "application/json"
        }
        
        logger.info(f"Fetching transcript for campaign_id={campaign_id} from {url}")
        
        with httpx.Client(timeout=30.0) as client:
            try:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                
                transcript = response.json()
                
                # #region agent log
                import json as json_lib
                with open(r'c:\Users\David Jekal\Desktop\Projekte\KI-Sellcruiting_VerarbeitungProtokollErgebnisse\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json_lib.dumps({"location":"questionnaire_client.py:95","message":"API response received","data":{"campaign_id":campaign_id,"response_keys":list(transcript.keys()),"has_pages":("pages" in transcript),"pages_count":len(transcript.get("pages",[])) if isinstance(transcript.get("pages"),list) else 0,"response_preview":str(transcript)[:500]},"timestamp":__import__('time').time()*1000,"sessionId":"debug-session","hypothesisId":"A,B,D"}) + '\n')
                # #endregion
                
                logger.info(f"Successfully fetched transcript for campaign {campaign_id}")
                
                return transcript
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching transcript: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error fetching transcript: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error fetching transcript: {e}")
                raise


"""HOC API Client for sending applicant/resume data."""
import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class HOCClient:
    """Client for HOC API integration."""
    
    def __init__(self):
        self.api_url = os.getenv("HOC_API_URL")
        self.api_key = os.getenv("HOC_API_KEY")
        
        if not self.api_url:
            logger.warning("HOC_API_URL not configured")
        if not self.api_key:
            logger.warning("HOC_API_KEY not configured")
    
    async def send_applicant(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send applicant and resume data to HOC API.
        
        Args:
            data: Result from pipeline_processor containing applicant and resume
            
        Returns:
            Response from HOC API
        """
        if not self.api_url or not self.api_key:
            raise ValueError("HOC API not configured (missing URL or API_KEY)")
        
        # Prepare payload for HOC
        payload = self._prepare_hoc_payload(data)
        
        # Send to HOC
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.api_url}/api/applicants",  # Adjust endpoint as needed
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                response.raise_for_status()
                
                logger.info(f"Successfully sent to HOC: Applicant {data['applicant_id']}")
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HOC API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error sending to HOC: {e}")
                raise
    
    def _prepare_hoc_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload in HOC's expected format.
        
        TODO: Adjust this based on actual HOC API specification.
        """
        # Current format matches the example structure provided
        # Adjust if HOC expects different field names/structure
        
        return {
            "applicant": data["applicant"],
            "resume": data["resume"]
        }


# Singleton instance
_hoc_client = None


def get_hoc_client() -> HOCClient:
    """Get or create HOC client singleton."""
    global _hoc_client
    if _hoc_client is None:
        _hoc_client = HOCClient()
    return _hoc_client


async def send_to_hoc(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to send data to HOC.
    
    Args:
        data: Result from pipeline_processor
        
    Returns:
        Response from HOC API
    """
    client = get_hoc_client()
    return await client.send_applicant(data)


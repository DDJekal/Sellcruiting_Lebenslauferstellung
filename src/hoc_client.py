"""HOC API Client for sending applicant/resume data."""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
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
        Send applicant data to HOC API via 3 separate endpoints.
        
        Args:
            data: Result from pipeline_processor containing applicant, resume, protocol, metadata
            
        Returns:
            Combined response from all three HOC API endpoints
        """
        if not self.api_url or not self.api_key:
            raise ValueError("HOC API not configured (missing URL or API_KEY)")
        
        campaign_id = data.get("campaign_id")
        if not campaign_id:
            raise ValueError("campaign_id is required for HOC API")
        
        results = {}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": self.api_key,  # Direct token (no "Bearer")
                "Content-Type": "application/json"
            }
            
            # 1. Send Transcript/Protocol to /api/v1/campaigns/{campaign_id}/transcript/
            try:
                transcript_payload = self._prepare_transcript_payload(data)
                response_transcript = await client.post(
                    f"{self.api_url}/campaigns/{campaign_id}/transcript/",
                    json=transcript_payload,
                    headers=headers
                )
                response_transcript.raise_for_status()
                results["transcript"] = response_transcript.json()
                logger.info(f"✅ Transcript sent to HOC: Campaign {campaign_id}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Transcript API error: {e.response.status_code} - {e.response.text}")
                results["transcript"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ Error sending transcript: {e}")
                results["transcript"] = {"error": str(e)}
            
            # 2. Send Resume to /api/v1/applicants/resume
            try:
                resume_payload = self._prepare_resume_payload(data)
                response_resume = await client.post(
                    f"{self.api_url}/applicants/resume",
                    json=resume_payload,
                    headers=headers
                )
                response_resume.raise_for_status()
                results["resume"] = response_resume.json()
                logger.info(f"✅ Resume sent to HOC: Applicant {data.get('applicant_id')}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Resume API error: {e.response.status_code} - {e.response.text}")
                results["resume"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ Error sending resume: {e}")
                results["resume"] = {"error": str(e)}
            
            # 3. Send Metadata to /api/v1/applicants/ai/call/meta
            try:
                meta_payload = self._prepare_meta_payload(data)
                response_meta = await client.post(
                    f"{self.api_url}/applicants/ai/call/meta",
                    json=meta_payload,
                    headers=headers
                )
                response_meta.raise_for_status()
                results["metadata"] = response_meta.json()
                logger.info(f"✅ Metadata sent to HOC: Conversation {data.get('conversation_id')}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Metadata API error: {e.response.status_code} - {e.response.text}")
                results["metadata"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ Error sending metadata: {e}")
                results["metadata"] = {"error": str(e)}
        
        # Log summary
        success_count = sum(1 for r in results.values() if "error" not in r)
        logger.info(f"📊 HOC API Summary: {success_count}/3 endpoints succeeded")
        
        return results
    
    def _prepare_transcript_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/campaigns/{campaign_id}/transcript/
        
        Format:
        {
          "conversation_id": "conv_...",
          "applicant_id": 89778,
          "protocol": {...},
          "timestamp": "2025-12-14T10:23:45Z"
        }
        """
        protocol = data.get("protocol_minimal", data.get("protocol", {}))
        
        return {
            "conversation_id": data.get("conversation_id"),
            "applicant_id": data.get("applicant_id"),
            "protocol": protocol,
            "timestamp": data.get("metadata", {}).get("processing", {}).get("timestamp")
        }
    
    def _prepare_resume_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/applicants/resume
        
        Format:
        {
          "applicant": {
            "id": 89778,
            "first_name": "David",
            "last_name": "Jekal",
            "email": "...",
            "phone": "+4915204465582",
            "postal_code": "..."
          },
          "resume": {
            "id": 90778,
            "applicant_id": 89778,  # <-- WICHTIG: applicant_id muss hier rein!
            "experiences": [...],
            "educations": [...],
            "motivation": "...",
            "expectations": "..."
          }
        }
        """
        applicant = data.get("applicant", {})
        resume = data.get("resume", {})
        applicant_id = data.get("applicant_id")
        
        # Add applicant_id to resume if not already present
        if applicant_id and "applicant_id" not in resume:
            resume["applicant_id"] = applicant_id
        
        return {
            "applicant": applicant,
            "resume": resume
        }
    
    def _prepare_meta_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/applicants/ai/call/meta
        
        Format:
        {
          "conversation_id": "conv_...",
          "campaign_id": "255",
          "applicant_id": 89778,
          "protocol_source": "api_campaign_255",
          "elevenlabs": {
            "agent_id": "agent_...",
            "call_duration_secs": 245,
            "call_duration_formatted": "4:05",
            "start_time_unix_secs": 1733988796,
            "start_time_formatted": "2025-12-12 08:15:20",
            "cost_cents": 12,
            "cost_formatted": "€0.12",
            "call_successful": true,
            "call_summary": "...",
            "termination_reason": "natural end",
            "candidate_first_name": "David",
            "candidate_last_name": "Jekal",
            "company_name": "...",
            "to_number": "+4915204465582",
            "agent_phone_number_id": "phnum_..."
          },
          "temporal_context": {
            "call_date": "2025-12-12",
            "call_year": 2025,
            "call_timestamp": 1733988796,
            "mentioned_years": [2021, 2019, 2023],
            "temporal_annotations_count": 15
          },
          "processing": {...},
          "files": {...}
        }
        """
        metadata = data.get("metadata", {})
        elevenlabs = metadata.get("elevenlabs", {})
        temporal_context = metadata.get("temporal_context", {})
        processing = metadata.get("processing", {})
        files = metadata.get("files", {})
        
        # Enrich elevenlabs with formatted values
        elevenlabs_enriched = self._enrich_elevenlabs_metadata(elevenlabs)
        
        # Enrich temporal context
        temporal_enriched = self._enrich_temporal_context(temporal_context, elevenlabs)
        
        return {
            "conversation_id": data.get("conversation_id"),
            "campaign_id": data.get("campaign_id"),
            "applicant_id": data.get("applicant_id"),
            "protocol_source": data.get("protocol_source", f"api_campaign_{data.get('campaign_id')}"),
            "elevenlabs": elevenlabs_enriched,
            "temporal_context": temporal_enriched,
            "processing": processing,
            "files": files
        }
    
    def _enrich_elevenlabs_metadata(self, elevenlabs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add formatted versions of ElevenLabs metadata.
        """
        enriched = elevenlabs.copy()
        
        # Format call duration (e.g., "4:05" from 245 seconds)
        if "call_duration_secs" in enriched:
            secs = enriched["call_duration_secs"]
            minutes = secs // 60
            seconds = secs % 60
            enriched["call_duration_formatted"] = f"{minutes}:{seconds:02d}"
        
        # Format start time (e.g., "2025-12-12 08:15:20" from unix timestamp)
        if "start_time_unix_secs" in enriched:
            timestamp = enriched["start_time_unix_secs"]
            dt = datetime.fromtimestamp(timestamp)
            enriched["start_time_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Format cost (e.g., "€0.12" from 12 cents)
        if "cost_cents" in enriched:
            cents = enriched["cost_cents"]
            euros = cents / 100
            enriched["cost_formatted"] = f"€{euros:.2f}"
        
        # Add call_successful if not present (infer from termination_reason)
        if "call_successful" not in enriched and "termination_reason" in enriched:
            enriched["call_successful"] = enriched["termination_reason"] == "natural end"
        
        return enriched
    
    def _enrich_temporal_context(self, temporal_context: Dict[str, Any], elevenlabs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add call_timestamp and temporal_annotations_count to temporal context.
        """
        enriched = temporal_context.copy()
        
        # Add call_timestamp from elevenlabs if not present
        if "call_timestamp" not in enriched and "start_time_unix_secs" in elevenlabs:
            enriched["call_timestamp"] = elevenlabs["start_time_unix_secs"]
        
        # Add temporal_annotations_count (placeholder - you might track this in pipeline)
        if "temporal_annotations_count" not in enriched:
            # Estimate based on mentioned_years length (actual count would come from temporal_enricher)
            enriched["temporal_annotations_count"] = len(enriched.get("mentioned_years", []))
        
        return enriched


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


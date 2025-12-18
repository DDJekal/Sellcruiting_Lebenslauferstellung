"""HOC API Client for sending applicant/resume data."""
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class HOCClient:
    """Client for HOC API integration."""
    
    def __init__(self):
        # Use HIRINGS_API_URL and HIRING_API_TOKEN (same API for both questionnaire and data submission)
        self.api_url = os.getenv("HIRINGS_API_URL")
        self.api_key = os.getenv("HIRING_API_TOKEN")
        
        if not self.api_url:
            logger.warning("HIRINGS_API_URL not configured")
        if not self.api_key:
            logger.warning("HIRING_API_TOKEN not configured")
    
    async def send_applicant(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send applicant data to HOC API via 3 separate endpoints.
        
        Args:
            data: Result from pipeline_processor containing applicant, resume, protocol, metadata
            
        Returns:
            Combined response from all three HOC API endpoints
        """
        if not self.api_url or not self.api_key:
            raise ValueError("HOC API not configured (missing HIRINGS_API_URL or HIRING_API_TOKEN)")
        
        campaign_id = data.get("campaign_id")
        if not campaign_id:
            raise ValueError("campaign_id is required for HOC API")
        
        applicant_data = data.get("applicant", {})
        logger.info(f"🚀 Starting HOC API submission for campaign_id={campaign_id}")
        logger.info(f"📊 Applicant: {applicant_data.get('first_name')} {applicant_data.get('last_name')}, phone: {applicant_data.get('phone')}")
        
        results = {}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": self.api_key,  # Direct token (no "Bearer")
                "Content-Type": "application/json"
            }
            
            # 1. Send Resume to /api/v1/applicants/resume (ZUERST - erstellt/findet Applicant!)
            try:
                resume_payload = self._prepare_resume_payload(data)
                logger.info(f"📤 [RESUME] Full payload: {json.dumps(resume_payload, ensure_ascii=False, default=str)}")
                response_resume = await client.post(
                    f"{self.api_url}/applicants/resume",
                    json=resume_payload,
                    headers=headers
                )
                response_resume.raise_for_status()
                results["resume"] = response_resume.json()
                logger.info(f"✅ [RESUME] Response: {results['resume']}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ [RESUME] API error: {e.response.status_code} - {e.response.text}")
                results["resume"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ [RESUME] Error: {e}")
                results["resume"] = {"error": str(e)}
            
            # 2. Send Transcript/Protocol to /api/v1/campaigns/{campaign_id}/transcript/ (ZWEITENS)
            try:
                transcript_payload = self._prepare_transcript_payload(data)
                logger.info(f"📤 [TRANSCRIPT] Full payload: {json.dumps(transcript_payload, ensure_ascii=False, default=str)}")
                response_transcript = await client.post(
                    f"{self.api_url}/campaigns/{campaign_id}/transcript/",
                    json=transcript_payload,
                    headers=headers
                )
                response_transcript.raise_for_status()
                results["transcript"] = response_transcript.json()
                logger.info(f"✅ [TRANSCRIPT] Response: {results['transcript']}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ [TRANSCRIPT] API error: {e.response.status_code} - {e.response.text}")
                results["transcript"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ [TRANSCRIPT] Error: {e}")
                results["transcript"] = {"error": str(e)}
            
            # 3. Send Metadata to /api/v1/applicants/ai/call/meta (DRITTENS)
            try:
                meta_payload = self._prepare_meta_payload(data)
                logger.info(f"📤 [METADATA] Full payload: {json.dumps(meta_payload, ensure_ascii=False, default=str)}")
                response_meta = await client.post(
                    f"{self.api_url}/applicants/ai/call/meta",
                    json=meta_payload,
                    headers=headers
                )
                response_meta.raise_for_status()
                results["metadata"] = response_meta.json()
                logger.info(f"✅ [METADATA] Response: {results['metadata']}")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ [METADATA] API error: {e.response.status_code} - {e.response.text}")
                results["metadata"] = {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"❌ [METADATA] Error: {e}")
                results["metadata"] = {"error": str(e)}
        
        # Log summary
        success_count = sum(1 for r in results.values() if "error" not in r)
        logger.info(f"📊 HOC API Summary: {success_count}/3 endpoints succeeded")
        
        return results
    
    def _prepare_transcript_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/campaigns/{campaign_id}/transcript/
        
        HOC API Format (applicant matching via first_name, last_name, phone):
        {
          "campaign_id": "639",
          "conversation_id": "conv_...",
          "applicant": {
            "first_name": "Test",
            "last_name": "Jekal",
            "phone": "+49 15204465582"
          },
          "pages": [...]
        }
        """
        protocol = data.get("protocol_minimal", data.get("protocol", {}))
        campaign_id = data.get("campaign_id")
        applicant_data = data.get("applicant", {})
        
        return {
            "campaign_id": str(campaign_id) if campaign_id else "",
            "conversation_id": data.get("conversation_id"),
            "applicant": {
                "first_name": applicant_data.get("first_name"),
                "last_name": applicant_data.get("last_name"),
                "phone": applicant_data.get("phone")
            },
            "pages": protocol.get("pages", [])
        }
    
    def _prepare_resume_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/applicants/resume
        
        Format:
        {
          "campaign_id": "255",
          "applicant": {
            "first_name": "David",
            "last_name": "Jekal",
            "email": "...",
            "phone": "+4915204465582",
            "postal_code": "..."
          },
          "resume": {
            "preferred_contact_time": "...",
            "preferred_workload": "...",
            "willing_to_relocate": "...",
            "earliest_start": "...",
            "current_job": "...",
            "motivation": "...",
            "expectations": "...",
            "start": "...",
            "experiences": [...],
            "educations": [...]
          }
        }
        """
        applicant = data.get("applicant", {}).copy()
        resume = data.get("resume", {}).copy()
        campaign_id = data.get("campaign_id")
        
        # WICHTIG: applicant.id NICHT senden - HOC API erstellt/findet Applicant!
        applicant.pop("id", None)
        
        # WICHTIG: resume.id und applicant_id NICHT senden - HOC API setzt automatisch!
        resume.pop("id", None)
        resume.pop("applicant_id", None)
        
        # WICHTIG: Keine IDs in experiences/educations - HOC API erstellt neue Einträge!
        if "experiences" in resume:
            for exp in resume["experiences"]:
                exp.pop("id", None)
        
        if "educations" in resume:
            for edu in resume["educations"]:
                edu.pop("id", None)
        
        return {
            "campaign_id": str(campaign_id) if campaign_id else "",
            "applicant": applicant,
            "resume": resume
        }
    
    def _prepare_meta_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for POST /api/v1/applicants/ai/call/meta
        
        HOC API Format (applicant matching via first_name, last_name, phone):
        {
          "conversation_id": "conv_...",
          "campaign_id": "255",
          "applicant": {
            "first_name": "Test",
            "last_name": "Jekal",
            "phone": "+49 15204465582"
          },
          "protocol_source": "api_campaign_255",
          "elevenlabs": {...},
          "temporal_context": {...},
          "processing": {...},
          "files": {...}
        }
        """
        metadata = data.get("metadata", {})
        elevenlabs = metadata.get("elevenlabs", {})
        temporal_context = metadata.get("temporal_context", {})
        processing = metadata.get("processing", {})
        files = metadata.get("files", {})
        applicant_data = data.get("applicant", {})
        
        # Enrich elevenlabs with formatted values
        elevenlabs_enriched = self._enrich_elevenlabs_metadata(elevenlabs)
        
        # Enrich temporal context
        temporal_enriched = self._enrich_temporal_context(temporal_context, elevenlabs)
        
        campaign_id = data.get("campaign_id")
        
        return {
            "conversation_id": data.get("conversation_id"),
            "campaign_id": str(campaign_id) if campaign_id else "",
            "applicant": {
                "first_name": applicant_data.get("first_name"),
                "last_name": applicant_data.get("last_name"),
                "phone": applicant_data.get("phone")
            },
            "protocol_source": data.get("protocol_source", f"api_campaign_{campaign_id}"),
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

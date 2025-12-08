"""Transformer for ElevenLabs post_call_transcription webhooks."""
from typing import Dict, Any, List
from pydantic import BaseModel


class ElevenLabsTranscriptItem(BaseModel):
    """Single transcript item from ElevenLabs."""
    role: str
    message: str
    time_in_call_secs: int


class ElevenLabsTransformer:
    """Transform ElevenLabs webhook data to internal transcript format."""
    
    def transform(self, elevenlabs_webhook: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Transform ElevenLabs post_call_transcription webhook to internal format.
        
        Args:
            elevenlabs_webhook: Full webhook payload from ElevenLabs
            
        Returns:
            List of transcript turns in format: [{"speaker": "A"|"B", "text": "..."}]
            
        Notes:
            - "user" role → speaker "A" (Kandidat)
            - "agent" role → speaker "B" (Recruiter/Agent)
            - Tool calls and null messages are filtered out
        """
        if elevenlabs_webhook.get("type") != "post_call_transcription":
            raise ValueError(
                f"Expected type 'post_call_transcription', got: {elevenlabs_webhook.get('type')}"
            )
        
        data = elevenlabs_webhook.get("data", {})
        transcript_raw = data.get("transcript", [])
        
        # Transform to internal format
        internal_transcript = []
        
        for item in transcript_raw:
            role = item.get("role")
            message = item.get("message")
            
            # Skip tool calls and empty messages
            if not message:
                continue
            
            # Map roles to speakers
            if role == "user":
                speaker = "A"  # Kandidat
            elif role == "agent":
                speaker = "B"  # Recruiter/Agent
            else:
                # Skip unknown roles
                continue
            
            internal_transcript.append({
                "speaker": speaker,
                "text": message
            })
        
        return internal_transcript
    
    def extract_metadata(self, elevenlabs_webhook: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract useful metadata from ElevenLabs webhook.
        
        Returns metadata like:
        - conversation_id
        - call_duration_secs
        - status
        - agent_id
        - start_time_unix_secs
        - cost (in cents)
        - dynamic_variables (candidate name, company, role, etc.)
        - call_summary
        - call_successful
        """
        data = elevenlabs_webhook.get("data", {})
        metadata_raw = data.get("metadata", {})
        analysis = data.get("analysis", {})
        client_data = data.get("conversation_initiation_client_data", {})
        dynamic_vars = client_data.get("dynamic_variables", {})
        
        return {
            "conversation_id": data.get("conversation_id"),
            "agent_id": data.get("agent_id"),
            "status": data.get("status"),
            "call_duration_secs": metadata_raw.get("call_duration_secs"),
            "start_time_unix_secs": metadata_raw.get("start_time_unix_secs"),
            "cost_cents": metadata_raw.get("cost"),
            "termination_reason": metadata_raw.get("termination_reason"),
            "call_successful": analysis.get("call_successful"),
            "call_summary": analysis.get("transcript_summary"),
            "call_summary_title": analysis.get("call_summary_title"),
            # Dynamic variables (candidate info)
            "candidate_first_name": dynamic_vars.get("candidatefirst_name"),
            "candidate_last_name": dynamic_vars.get("candidatelast_name"),
            "company_name": dynamic_vars.get("companyname"),
            "campaign_role_title": dynamic_vars.get("campaignrole_title"),
            "campaign_location": dynamic_vars.get("campaignlocation_label"),
            "company_priorities": dynamic_vars.get("companypriorities"),
            "company_pitch": dynamic_vars.get("companypitch"),
        }


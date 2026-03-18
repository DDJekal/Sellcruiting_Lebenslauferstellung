"""Transformer for WhatsApp chat sessions to internal transcript format.

Converts completed WhatsApp sessions (from the whatsapp_sessions DB table)
into the same internal format used by ElevenLabsTransformer, so they can
feed into the existing pipeline (Extractor, ResumeBuilder, etc.).

Internal format: [{"speaker": "A"|"B", "text": "..."}]
  - "A" = Kandidat (user)
  - "B" = Recruiter/Agent (agent)
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class WhatsAppTransformer:
    """Transform WhatsApp session data to internal transcript format."""
    
    def transform(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Transform WhatsApp messages to internal transcript format.
        
        Args:
            messages: List of message dicts from whatsapp_sessions.messages JSONB
                     Format: [{"role": "user"|"agent", "content": "...", "timestamp": "..."}]
        
        Returns:
            List of transcript turns: [{"speaker": "A"|"B", "text": "..."}]
        """
        internal_transcript = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if not content:
                continue
            
            # Skip system/template log entries
            if content.startswith("[Template message sent:"):
                continue
            
            if role == "user":
                speaker = "A"  # Kandidat
            elif role == "agent":
                speaker = "B"  # Recruiter/Agent
            else:
                continue
            
            internal_transcript.append({
                "speaker": speaker,
                "text": content
            })
        
        return internal_transcript
    
    def extract_metadata(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from a WhatsApp session in the same format
        as ElevenLabsTransformer.extract_metadata().
        
        This ensures compatibility with the downstream pipeline.
        
        Args:
            session: Full session dict from whatsapp_sessions table
            
        Returns:
            Metadata dict compatible with the pipeline
        """
        # Calculate duration from first to last message
        created_at = session.get("created_at")
        completed_at = session.get("completed_at") or session.get("last_message_at")
        
        duration_secs = None
        if created_at and completed_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            if isinstance(completed_at, str):
                completed_at = datetime.fromisoformat(completed_at)
            duration_secs = int((completed_at - created_at).total_seconds())
        
        start_time_unix = None
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            start_time_unix = int(created_at.timestamp())
        
        return {
            "conversation_id": session.get("conversation_id"),
            "agent_id": None,
            "status": session.get("status"),
            "call_duration_secs": duration_secs,
            "start_time_unix_secs": start_time_unix,
            "cost_cents": None,
            "termination_reason": f"whatsapp_{session.get('status', 'unknown')}",
            "call_successful": "success" if session.get("status") == "completed" else None,
            "call_summary": None,
            "call_summary_title": None,
            # Candidate info
            "candidate_first_name": session.get("candidate_first_name"),
            "candidate_last_name": session.get("candidate_last_name"),
            "company_name": session.get("company_name"),
            "campaign_role_title": session.get("campaign_role_title"),
            "campaign_location": None,
            "company_priorities": None,
            "company_pitch": None,
            # IDs
            "campaign_id": session.get("campaign_id"),
            "applicant_id": session.get("applicant_id"),
            "to_number": session.get("to_number"),
            "agent_phone_number_id": None,
            # WhatsApp-specific
            "channel": "whatsapp",
            "whatsapp_session_id": session.get("id"),
            "trigger_reason": session.get("trigger_reason"),
        }

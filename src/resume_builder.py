"""Resume builder for extracting structured CV data from transcripts."""
import os
import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from openai import OpenAI

from models import (
    ApplicantResume, Applicant, Resume, 
    Experience, Education
)


class ResumeBuilder:
    """Builds structured resume from transcript and metadata."""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key."""
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    
    def build_resume(
        self,
        transcript: List[Dict[str, str]],
        elevenlabs_metadata: Optional[Dict[str, Any]] = None,
        temporal_context: Optional[Dict[str, Any]] = None
    ) -> ApplicantResume:
        """
        Build structured resume from transcript.
        
        Args:
            transcript: Enriched transcript with temporal annotations
            elevenlabs_metadata: Metadata from ElevenLabs (optional)
            temporal_context: Temporal context from enricher
            
        Returns:
            ApplicantResume with structured data
        """
        # Generate IDs
        applicant_id = self._generate_id(elevenlabs_metadata)
        resume_id = applicant_id + 1000  # Simple offset
        
        # Extract applicant data
        applicant = self._extract_applicant_data(
            transcript, elevenlabs_metadata, applicant_id
        )
        
        # Extract resume data with LLM
        resume_data = self._extract_resume_data(
            transcript, temporal_context, applicant_id, resume_id
        )
        
        return ApplicantResume(
            applicant=applicant,
            resume=resume_data
        )
    
    def _generate_id(self, metadata: Optional[Dict[str, Any]]) -> int:
        """Generate unique ID from metadata or random."""
        if metadata and metadata.get('conversation_id'):
            # Hash conversation_id to int
            hash_obj = hashlib.md5(metadata['conversation_id'].encode())
            return int(hash_obj.hexdigest()[:8], 16) % 1000000
        else:
            # Fallback: timestamp-based
            return int(datetime.now().timestamp()) % 1000000
    
    def _extract_applicant_data(
        self,
        transcript: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]],
        applicant_id: int
    ) -> Applicant:
        """Extract applicant personal data."""
        
        # Start with metadata if available
        first_name = None
        last_name = None
        email = None
        phone = None
        postal_code = None
        
        if metadata:
            first_name = metadata.get('candidate_first_name')
            last_name = metadata.get('candidate_last_name')
        
        # Extract missing fields from transcript
        full_text = ' '.join(turn.get('text', '') for turn in transcript)
        
        # Simple extraction (could be enhanced with LLM)
        import re
        
        # Extract postal code (German format: 5 digits)
        if not postal_code:
            plz_match = re.search(r'\b(\d{5})\b', full_text)
            if plz_match:
                postal_code = plz_match.group(1)
        
        # Extract phone (German format)
        if not phone:
            phone_match = re.search(r'\+?49\s*\d{2,4}\s*\d{6,8}', full_text)
            if phone_match:
                phone = phone_match.group(0)
        
        # Extract email
        if not email:
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', full_text)
            if email_match:
                email = email_match.group(0)
        
        return Applicant(
            id=applicant_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            postal_code=postal_code
        )
    
    def _extract_resume_data(
        self,
        transcript: List[Dict[str, str]],
        temporal_context: Optional[Dict[str, Any]],
        applicant_id: int,
        resume_id: int
    ) -> Resume:
        """Extract structured resume data using LLM."""
        
        system_prompt = self._build_resume_extraction_prompt()
        user_prompt = self._build_transcript_context(transcript, temporal_context)
        
        try:
            response = self.client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Parse experiences
            experiences = []
            for i, exp in enumerate(result.get('experiences', []), start=1):
                experiences.append(Experience(
                    id=i,
                    start=exp.get('start'),
                    end=exp.get('end'),
                    company=exp.get('company', ''),
                    tasks=exp.get('tasks', '')
                ))
            
            # Parse educations
            educations = []
            for i, edu in enumerate(result.get('educations', []), start=1):
                educations.append(Education(
                    id=i,
                    end=edu.get('end'),
                    company=edu.get('company', ''),
                    description=edu.get('description', '')
                ))
            
            return Resume(
                id=resume_id,
                preferred_contact_time=result.get('preferred_contact_time'),
                preferred_workload=result.get('preferred_workload'),
                willing_to_relocate=result.get('willing_to_relocate'),
                earliest_start=result.get('earliest_start'),
                current_job=result.get('current_job'),
                motivation=result.get('motivation'),
                expectations=result.get('expectations'),
                start=result.get('start'),
                applicant_id=applicant_id,
                experiences=experiences,
                educations=educations
            )
            
        except Exception as e:
            print(f"   [WARN] Resume-Extraktion fehlgeschlagen: {e}")
            # Return minimal resume
            return Resume(
                id=resume_id,
                applicant_id=applicant_id,
                experiences=[],
                educations=[]
            )
    
    def _build_resume_extraction_prompt(self) -> str:
        """Build system prompt for resume extraction."""
        return """Du bist ein Experte für die Extraktion von strukturierten Lebenslaufdaten aus Bewerbungsgesprächen.

AUFGABE:
Extrahiere aus dem deutschen Transkript alle relevanten Lebenslaufdaten und gib sie als strukturiertes JSON zurück.

WICHTIG - TEMPORALE ANNOTATIONEN:
- Das Transkript enthält temporale Annotationen in eckigen Klammern: [≈2021, vor 3 J]
- Nutze diese Annotationen für präzise Datumsangaben
- Konvertiere relative Zeitangaben zu ISO-Daten (YYYY-MM-DD)
- Bei "seit X" ohne Enddatum: end = null (bedeutet "bis heute")

FELDER:
- preferred_contact_time: Bevorzugte Erreichbarkeit (z.B. "Abends (18:00-21:00)")
- preferred_workload: "Full-time", "Part-time", "Flexible", etc.
- willing_to_relocate: "ja", "nein", oder null
- earliest_start: Frühester Starttermin (ISO-Date oder null)
- current_job: Aktuelle Position und Firma
- motivation: Motivation für den Wechsel (Stichpunkte mit -)
- expectations: Erwartungen an neuen Arbeitgeber (Stichpunkte mit -)
- start: Gewünschtes Startdatum (ISO-Date)
- experiences: Array von Berufserfahrungen
- educations: Array von Ausbildungen/Qualifikationen

EXPERIENCES Format:
{
  "start": "YYYY-MM-DD" oder null,
  "end": "YYYY-MM-DD" oder null (null = aktuell),
  "company": "Firmenname",
  "tasks": "Detaillierte Beschreibung der Aufgaben und Verantwortlichkeiten"
}

EDUCATIONS Format:
{
  "end": "YYYY-MM-DD" oder null,
  "company": "Institution/Organisation",
  "description": "Abschluss, Qualifikation oder Kursname"
}

OUTPUT JSON Schema:
{
  "preferred_contact_time": string|null,
  "preferred_workload": string|null,
  "willing_to_relocate": "ja"|"nein"|null,
  "earliest_start": "YYYY-MM-DD"|null,
  "current_job": string|null,
  "motivation": string|null,
  "expectations": string|null,
  "start": "YYYY-MM-DD"|null,
  "experiences": [...],
  "educations": [...]
}

REGELN:
- Nur Fakten aus dem Transkript extrahieren, keine Erfindungen
- Bei Unsicherheit: null verwenden
- Temporale Annotationen für genaue Daten nutzen
- Motivation/Erwartungen als Stichpunkte mit "-" formatieren
"""
    
    def _build_transcript_context(
        self,
        transcript: List[Dict[str, str]],
        temporal_context: Optional[Dict[str, Any]]
    ) -> str:
        """Build context for LLM extraction."""
        
        context = ""
        
        if temporal_context:
            context += f"""TEMPORALER KONTEXT:
- Referenzdatum des Gesprächs: {temporal_context.get('call_date')}
- Jahr des Gesprächs: {temporal_context.get('call_year')}
- Erwähnte Jahre im Transkript: {temporal_context.get('mentioned_years', [])}

"""
        
        context += "TRANSKRIPT:\n"
        for i, turn in enumerate(transcript):
            speaker_label = "Kandidat" if turn['speaker'] == 'A' else "Recruiter"
            context += f"[{i}] {speaker_label}: {turn['text']}\n"
        
        context += "\n\nExtrahiere nun die strukturierten Lebenslaufdaten als JSON:"
        
        return context



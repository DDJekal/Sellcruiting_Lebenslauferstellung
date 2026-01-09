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
            # Extract phone from ElevenLabs to_number (the phone number that was called)
            phone = metadata.get('to_number')
        
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
                    position=exp.get('position'),
                    start=exp.get('start'),
                    end=exp.get('end'),
                    company=exp.get('company') or None,  # Explicitly allow None
                    employment_type=exp.get('employment_type'),
                    tasks=exp.get('tasks', '')
                ))
            
            # Parse educations
            educations = []
            for i, edu in enumerate(result.get('educations', []), start=1):
                educations.append(Education(
                    id=i,
                    end=edu.get('end'),
                    company=edu.get('company') or None,  # Explicitly allow None
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

═══════════════════════════════════════════════════════════════════
TEMPORALE REGELN (HÖCHSTE PRIORITÄT)
═══════════════════════════════════════════════════════════════════

1. ANNOTATIONEN NUTZEN:
   - Das Transkript enthält temporale Annotationen: [≈2021, vor 3 J]
   - Diese haben HÖCHSTE PRIORITÄT für Datumsangaben

2. FORMATIERUNG:
   - "seit 2021" → start: "2021-01-01", end: null
   - "von 2019 bis 2023" → start: "2019-01-01", end: "2023-12-31"
   - "vor 3 Jahren [≈2021]" → start: "2021-01-01"
   - "Mitte 2020" → "2020-06-01"
   - "Ende 2022" → "2022-12-01"
   - "Anfang 2019" → "2019-01-01"
   - "noch bis 2025" → end: "2025-12-31"

3. VALIDIERUNG (KRITISCH):
   - start muss IMMER vor end liegen
   - Bei ungültigen Daten: null verwenden + NOTE
   - Keine Überlappungen bei Vollzeitjobs
   - Experiences chronologisch (neueste zuerst)

═══════════════════════════════════════════════════════════════════
EXPERIENCES - QUALITÄTS-ANFORDERUNGEN
═══════════════════════════════════════════════════════════════════

1. VOLLSTÄNDIGKEIT:
   ✅ Durchsuche GESAMTES Transkript systematisch
   ✅ Jede erwähnte Position ist eine Experience
   ✅ Auch kurze Praktika/Nebenjobs/Werkstudententätigkeit
   ✅ Chronologisch sortieren (neueste zuerst)

2. TASKS-FELD - DETAILLIERT (MINIMUM 100 ZEICHEN):
   Extrahiere und strukturiere:
   - Konkrete Aufgaben (z.B. "Kundenberatung", "Projektleitung")
   - Technologien/Tools (z.B. "Python", "SAP", "Excel")
   - Verantwortungsbereiche (z.B. "Team von 5 Personen")
   - Errungenschaften (z.B. "Umsatzsteigerung um 20%")
   - Branchen/Bereiche (z.B. "im Bereich E-Commerce")
   - SCHWERPUNKTE erkennbar machen (z.B. "Schwerpunkt: Hardwarekonstruktion")
   
   ⚠️ FORMAT: Fließtext mit Semikolon-Trennung (KEIN "- " am Anfang!)
   MINDESTLÄNGE: 100 Zeichen pro Experience (STRENG!)
   
   ⚠️ KRITISCHE REGEL: 
   - Jede Experience MUSS mindestens 100 Zeichen im tasks-Feld haben
   - Wenn nur wenig Info im Transkript: Erweitere mit typischen Aufgaben für die Position
   - Format: Fließtext, einzelne Tätigkeiten mit Semikolon getrennt
   
   ✅ GUT - Detailliert mit Schwerpunkt (210 Zeichen):
   "Hardwarekonstruktion für Kundenanlagen (Schwerpunkt: Automatisierungstechnik); Integration von Kundenwünschen in Anlagendesigns; Kundenaustausch und technische Beratung; Prozessoptimierung zur Automatisierung von Betriebsabläufen; Sonderaufgaben im Bereich Digitalisierung"
   
   ✅ GUT - Auch bei wenig Info erweitert (187 Zeichen):
   "Entwicklung von Python-basierten Automatisierungsskripten für Datenverarbeitung; Projektkoordination zwischen IT-Abteilung und Fachabteilungen; Betreuung und Mentoring von 3 Junior-Entwicklern; Implementierung agiler Methoden (Scrum, Kanban) im Team"
   
   ❌ SCHLECHT - Mit Aufzählungszeichen (veraltet):
   "- Patientenbetreuung in der Inneren Medizin\n- Medikamentenvergabe und Wundversorgung"
   
   ❌ SCHLECHT - Zu vage (31 Zeichen):
   "Arbeit in der Inneren Medizin"
   
   ❌ INAKZEPTABEL - Unter 100 Zeichen:
   "Entwicklung und Projektarbeit" (28 Zeichen)

3. POSITION-FELD (KRITISCH - PFLICHTFELD):
   ✅ Extrahiere die GENAUE Berufsbezeichnung:
   - "Konstrukteur" (nicht "Arbeit in der Konstruktion")
   - "Werkstudent Hardwarekonstruktion"
   - "Projektleiter Elektrotechnik"
   - "Pflegefachkraft"
   - "Software-Entwickler"
   
   ❌ Keine vagen Beschreibungen wie:
   - "Arbeit in der Konstruktion"
   - "tätig in..."
   - "im Bereich..."

4. COMPANY-FELD - VOLLSTÄNDIGER FIRMENNAME:
   ✅ Immer den VOLLSTÄNDIGEN Firmennamen extrahieren:
   - "Windmüller und Hölscher GmbH, Lengrich"
   - "Siemens AG"
   - "Klinikum der Stadt Köln"
   
   ❌ NICHT AKZEPTABEL:
   - "eine Firma"
   - "ein Unternehmen"
   - "Firma XY"
   
   ⚠️ Bei unklarem Namen: null (nicht raten!)

5. EMPLOYMENT_TYPE-FELD (NEU - WICHTIG):
   Unterscheide klar zwischen verschiedenen Beschäftigungsarten:
   - "Hauptjob" (Vollzeit-Hauptbeschäftigung)
   - "Nebenjob" (geringfügige Beschäftigung parallel zu Hauptjob)
   - "Werkstudent" (während Studium, meist 15-20h/Woche)
   - "Duales Studium" (Kombination Arbeit + Studium, oft 3 Tage/Woche)
   - "Praktikum" (befristete Lernphase)
   - "Ausbildung" (Berufsausbildung)
   
   HINWEIS: 
   - Sortiere Experiences nach Start-Datum (neueste zuerst)
   - Markiere aber Haupt- vs. Nebenjobs im employment_type Feld
   - So ist erkennbar, was parallel lief

6. BEISPIEL VOLLSTÄNDIGE EXPERIENCE:
{
  "position": "Werkstudent Hardwarekonstruktion",
  "start": "2021-08-01",
  "end": null,
  "company": "Windmüller und Hölscher GmbH, Lengrich",
  "employment_type": "Duales Studium",
  "tasks": "Hardwarekonstruktion für Kundenanlagen (Schwerpunkt: Automatisierungstechnik); Integration von Kundenwünschen in bestehende Anlagendesigns; Kundenaustausch und technische Beratung; Prozessoptimierung zur Automatisierung von Betriebsabläufen; Sonderaufgaben im Bereich Digitalisierung"
}

═══════════════════════════════════════════════════════════════════
EDUCATIONS - VOLLSTÄNDIGKEIT (KRITISCH)
═══════════════════════════════════════════════════════════════════

1. ALLE AUSBILDUNGEN ERFASSEN (PFLICHT):
   ✅ Schulbildung (WICHTIG - oft vergessen!):
   - Abitur (mit Schule und Jahr)
   - Realschulabschluss
   - Fachabitur
   
   ✅ Berufsausbildung:
   - Ausbildung zum/zur...
   - IHK-Abschlüsse
   
   ✅ Hochschulbildung:
   - Bachelor/Master/Diplom
   - Hochschule/Universität MIT VOLLSTÄNDIGEM NAMEN
   
   ✅ Weiterbildungen/Zertifikate
   ✅ Kurse (wenn relevant)
   
   ⚠️ KRITISCHE REGEL:
   - Durchsuche GESAMTES Transkript nach ALLEN Bildungsstationen
   - Auch beiläufige Erwähnungen: "hab Abi gemacht", "war auf dem Gymnasium"
   - Schule NICHT vergessen! Oft im ersten Drittel des Gesprächs erwähnt

2. DESCRIPTION-FELD - PRÄZISE:
   ✅ GUT:
   - "Abitur (Note: 2,3)" (wenn Note erwähnt)
   - "Bachelor of Science Elektrotechnik"
   - "Ausbildung zum Fachinformatiker Systemintegration"
   - "Zertifizierung: AWS Solutions Architect"
   
   ❌ SCHLECHT:
   - "Studium" (zu vage - welcher Abschluss?)
   - "Schule" (zu vage - welcher Abschluss?)

3. COMPANY-FELD - VOLLSTÄNDIGER INSTITUTIONSNAME (PFLICHT):
   ✅ GUT:
   - "Hochschule Osnabrück am Westerberg"
   - "Gymnasium Musterhausen"
   - "TU München"
   - "IHK Köln"
   
   ❌ NICHT AKZEPTABEL:
   - "Hochschule" (ohne Name)
   - "Uni" (ohne Name)
   - null (wenn Institution im Transkript genannt wurde!)

═══════════════════════════════════════════════════════════════════
WEITERE FELDER
═══════════════════════════════════════════════════════════════════

- preferred_contact_time: z.B. "Nachmittags (15:00-17:00)", "Werktags ab 17 Uhr", "Abends"
- preferred_workload: 
  ⚠️ WICHTIG: Bei Teilzeit IMMER Stundenzahl angeben!
  Beispiele:
  - "Vollzeit (40h/Woche)"
  - "Teilzeit (20h/Woche)"
  - "Teilzeit (25 Stunden pro Woche)"
  - "3 Tage die Woche" → umrechnen zu "Teilzeit (ca. 24h/Woche)"
  - "Flexible Arbeitszeit"
- willing_to_relocate: "ja", "nein", oder null (wenn nicht erwähnt)
- earliest_start: Frühester Starttermin (ISO-Date oder null)
- current_job: z.B. "Konstrukteur bei Windmüller und Hölscher" (Position + Firma)
- motivation: Stichpunkte mit "- " (z.B. "- Mehr Verantwortung\n- Bessere Work-Life-Balance")
- expectations: Stichpunkte mit "- " (z.B. "- Homeoffice-Möglichkeit\n- Weiterbildungsbudget")
- start: Gewünschtes Startdatum (ISO-Date oder null)

═══════════════════════════════════════════════════════════════════
QUALITÄTSPRÜFUNG (SELBST-VALIDIERUNG)
═══════════════════════════════════════════════════════════════════

Vor dem Senden überprüfen:
1. ✅ Alle Daten temporal gültig? (start < end)
2. ✅ JEDE Experience mit mind. 100 Zeichen in tasks? (KRITISCH!)
3. ✅ JEDE Experience hat position-Feld ausgefüllt? (KRITISCH!)
4. ✅ JEDE Experience hat vollständigen Firmennamen in company? (KRITISCH!)
5. ✅ Alle erwähnten Jobs erfasst?
6. ✅ Alle erwähnten Bildungsstationen erfasst (inkl. Schule!)? (KRITISCH!)
7. ✅ Wenn "current_job" → muss Experience mit end=null existieren
8. ✅ Keine Halluzinationen? (nur Transkript-Fakten)
9. ✅ Bei Teilzeit: Stundenzahl angegeben? (KRITISCH!)

⚠️ WARNUNG: 
- Experiences mit tasks < 100 Zeichen werden ABGELEHNT!
- Tasks mit "- " am Anfang werden ABGELEHNT (nutze Semikolon-Format)!
- Experiences ohne position werden ABGELEHNT!
- Vage Firmennamen ("eine Firma") werden ABGELEHNT!

═══════════════════════════════════════════════════════════════════
OUTPUT JSON SCHEMA
═══════════════════════════════════════════════════════════════════

{
  "preferred_contact_time": string|null,
  "preferred_workload": string|null (z.B. "Vollzeit (40h/Woche)" oder "Teilzeit (25h/Woche)" - bei Teilzeit IMMER mit Stundenzahl!),
  "willing_to_relocate": "ja"|"nein"|null,
  "earliest_start": "YYYY-MM-DD"|null,
  "current_job": string|null,
  "motivation": string|null,
  "expectations": string|null,
  "start": "YYYY-MM-DD"|null,
  "experiences": [
    {
      "position": string (PFLICHT - Berufsbezeichnung, z.B. "Konstrukteur", "Werkstudent Hardwarekonstruktion"),
      "start": "YYYY-MM-DD"|null,
      "end": "YYYY-MM-DD"|null,
      "company": string (PFLICHT - vollständiger Firmenname, z.B. "Windmüller und Hölscher GmbH, Lengrich"),
      "employment_type": string (z.B. "Hauptjob", "Nebenjob", "Werkstudent", "Duales Studium", "Praktikum"),
      "tasks": string (Fließtext mit Semikolon-Trennung, KEIN "- " am Anfang!, MINIMUM 100 Zeichen, Schwerpunkt erkennbar!)
    }
  ],
  "educations": [
    {
      "end": "YYYY-MM-DD"|null,
      "company": string (PFLICHT - vollständiger Institutionsname, z.B. "Hochschule Osnabrück", "Gymnasium Musterhausen"),
      "description": string (präzise Bezeichnung, z.B. "Bachelor Elektrotechnik", "Abitur", "Realschulabschluss")
    }
  ]
}

KRITISCHE REGELN:
❌ KEINE Erfindungen - nur Transkript-Fakten
❌ KEINE "- " am Anfang von tasks (nutze Semikolon-Format)
❌ KEINE vagen tasks-Beschreibungen (<100 Zeichen)
❌ KEINE vagen Firmennamen ("eine Firma", "ein Unternehmen")
❌ KEINE fehlenden Schulen/Unis wenn im Transkript erwähnt
❌ KEINE fehlenden Stundenzahlen bei Teilzeit
❌ KEINE fehlenden position-Felder
✅ Bei Unsicherheit bei company/position: null verwenden (aber nur wenn wirklich unklar!)
✅ Temporale Annotationen [≈Jahr] nutzen
✅ JEDE Experience detailliert beschreiben mit erkennbarem Schwerpunkt
✅ Position IMMER als konkrete Berufsbezeichnung
✅ Hauptjob vs Nebenjob durch employment_type unterscheiden
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



















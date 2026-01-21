"""Resume builder for extracting structured CV data from transcripts."""
import os
import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from models import (
    ApplicantResume, Applicant, Resume, 
    Experience, Education
)
from llm_client import LLMClient


class ResumeBuilder:
    """Builds structured resume from transcript and metadata."""
    
    def __init__(self, api_key: str = None, prefer_claude: bool = True):
        """
        Initialize with LLM client.
        
        Args:
            api_key: Deprecated (uses env vars now)
            prefer_claude: Use Claude Sonnet 4.5 primary, GPT-4o fallback
        """
        self.llm_client = LLMClient(prefer_claude=prefer_claude)
    
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
        
        # Extract applicant data (basic info from metadata + regex)
        applicant = self._extract_applicant_data(
            transcript, elevenlabs_metadata, applicant_id
        )
        
        # Extract resume data with LLM (includes postal_code extraction)
        resume_data = self._extract_resume_data(
            transcript, temporal_context, applicant_id, resume_id
        )
        
        # Update applicant postal_code from LLM if available
        # (LLM is more accurate than regex)
        if resume_data.postal_code and not applicant.postal_code:
            print(f"   [INFO] Uebertrage PLZ vom Resume zum Applicant: {resume_data.postal_code}")
            applicant.postal_code = resume_data.postal_code
        elif resume_data.postal_code and applicant.postal_code != resume_data.postal_code:
            print(f"   [INFO] LLM-PLZ ({resume_data.postal_code}) ueberschreibt Regex-PLZ ({applicant.postal_code})")
            applicant.postal_code = resume_data.postal_code
        
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
            # Use Claude with OpenAI fallback
            response_text = self.llm_client.create_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=4000
            )
            
            result = json.loads(response_text)
            
            # Parse experiences with validation
            experiences = []
            for i, exp in enumerate(result.get('experiences', []), start=1):
                # VALIDATION: Ensure position is present (CRITICAL!)
                position = exp.get('position')
                if not position:
                    print(f"   [ERROR] Experience {i} OHNE 'position'-Feld - KRITISCHER FEHLER!")
                    
                    # Try intelligent fallback: extract from employment_type or tasks
                    employment_type = exp.get('employment_type', '')
                    tasks = exp.get('tasks', '')
                    
                    # Fallback 1: Use employment_type if it's descriptive
                    if employment_type and employment_type not in ['Hauptjob', 'Nebenjob', 'Praktikum']:
                        position = employment_type
                        print(f"   [FALLBACK] Position aus employment_type: '{position}'")
                    
                    # Fallback 2: Try to extract from tasks using keyword mapping
                    elif tasks:
                        position = self._extract_position_from_keywords(tasks)
                        if position:
                            print(f"   [FALLBACK] Position aus tasks extrahiert: '{position}'")
                        else:
                            print(f"   [FALLBACK FAILED] Keine Position extrahierbar - Experience wird übersprungen!")
                            continue  # Skip this experience
                    else:
                        print(f"   [FALLBACK FAILED] Experience ohne position wird übersprungen!")
                        continue  # Skip this experience
                    
                    exp['position'] = position
                
                # Validate that position is not vague and improve if possible
                if position and any(vague in position.lower() for vague in ['arbeit in', 'tätig in', 'tätig als', 'im bereich']):
                    print(f"   [WARN] Vage Position erkannt: '{position}' - versuche zu verbessern")
                    improved = self._extract_position_from_keywords(position)
                    if improved:
                        position = improved
                        exp['position'] = position
                        print(f"   [FIX] Position verbessert zu: '{position}'")
                    else:
                        print(f"   [WARN] Konnte vage Position nicht verbessern: '{position}'")
                
                # Clean vague company names
                company = exp.get('company')
                if company and company.lower() in ["eine firma", "ein unternehmen", "firma", "unternehmen"]:
                    print(f"   [WARN] Vage Firmenbezeichnung '{company}' -> null")
                    company = None
                
                # Validate tasks length
                tasks = exp.get('tasks', '')
                if tasks and len(tasks) < 100:
                    print(f"   [WARN] Tasks zu kurz ({len(tasks)} Zeichen) fuer: {exp.get('position')}")
                
                experiences.append(Experience(
                    id=i,
                    position=position,  # Now guaranteed to exist
                    start=exp.get('start'),
                    end=exp.get('end'),
                    company=company,
                    employment_type=exp.get('employment_type'),
                    tasks=tasks
                ))
            
            # Parse educations
            educations = []
            for i, edu in enumerate(result.get('educations', []), start=1):
                educations.append(Education(
                    id=i,
                    end=edu.get('end'),
                    company=edu.get('company') or None,
                    description=edu.get('description', '')
                ))
            
            # Extract postal_code and city from LLM
            postal_code_llm = result.get('postal_code')
            city_llm = result.get('city')
            
            # FALLBACK: If LLM didn't find PLZ, try regex as backup
            if not postal_code_llm:
                print(f"   [WARN] LLM fand keine PLZ - versuche Regex-Fallback")
                full_text = ' '.join(turn.get('text', '') for turn in transcript)
                
                # Find all 5-digit numbers
                import re
                plz_matches = re.findall(r'\b(\d{5})\b', full_text)
                
                # Filter for PLZ context (near keywords like "postleitzahl", "plz", "wohne")
                plz_keywords = ['postleitzahl', 'plz', 'wohne', 'wohnort', 'gezogen', 'umgezogen']
                
                # Try to find PLZ near context keywords
                for match in plz_matches:
                    # Find context around this match
                    match_pos = full_text.find(match)
                    if match_pos > 0:
                        context_before = full_text[max(0, match_pos-100):match_pos].lower()
                        context_after = full_text[match_pos:min(len(full_text), match_pos+100)].lower()
                        context = context_before + context_after
                        
                        # Check if any PLZ keyword is in context
                        if any(keyword in context for keyword in plz_keywords):
                            postal_code_llm = match
                            print(f"   [FALLBACK] PLZ aus Regex extrahiert: {postal_code_llm}")
                            break
                
                # If still not found, take first 5-digit number (risky but better than nothing)
                if not postal_code_llm and plz_matches:
                    postal_code_llm = plz_matches[0]
                    print(f"   [FALLBACK] PLZ aus erster 5-stelliger Zahl: {postal_code_llm}")
            else:
                print(f"   [INFO] PLZ aus LLM extrahiert: {postal_code_llm}")
            
            if city_llm:
                print(f"   [INFO] Stadt aus LLM extrahiert: {city_llm}")
            
            return Resume(
                id=resume_id,
                postal_code=postal_code_llm,
                city=city_llm,
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
    
    def _extract_position_from_keywords(self, text: str) -> str:
        """
        Extract job position from text using keyword mapping.
        
        Args:
            text: Text containing job-related keywords
            
        Returns:
            Extracted position or None if no match found
        """
        POSITION_KEYWORDS = {
            'konstruktion': 'Konstrukteur',
            'konstrukteur': 'Konstrukteur',
            'hardwarekonstruktion': 'Hardwarekonstrukteur',
            'pflege': 'Pflegefachkraft',
            'krankenpflege': 'Gesundheits- und Krankenpfleger',
            'altenpflege': 'Altenpfleger',
            'kinderpflege': 'Kinderpfleger',
            'intensivpflege': 'Pflegefachkraft Intensivstation',
            'kita-leitung': 'Kita-Leitung',
            'kita leitung': 'Kita-Leitung',
            'kitaleitung': 'Kita-Leitung',
            'stellvertretende kita-leitung': 'Stellvertretende Kita-Leitung',
            'erzieher': 'Erzieher',
            'erzieherin': 'Erzieherin',
            'entwicklung': 'Entwickler',
            'softwareentwicklung': 'Software-Entwickler',
            'webentwicklung': 'Web-Entwickler',
            'vertrieb': 'Vertriebsmitarbeiter',
            'verkauf': 'Verkäufer',
            'buchhaltung': 'Buchhalter',
            'verwaltung': 'Verwaltungsmitarbeiter',
            'sekretariat': 'Sekretär',
            'assistenz': 'Assistent',
            'projektleitung': 'Projektleiter',
            'teamleitung': 'Teamleiter',
            'abteilungsleitung': 'Abteilungsleiter',
            'geschäftsführung': 'Geschäftsführer',
            'pädagogik': 'Pädagogische Fachkraft',
            'sozialpädagogik': 'Sozialpädagoge',
            'gastronomie': 'Gastronomiefachkraft',
            'küche': 'Koch',
            'service': 'Servicekraft',
            'lager': 'Lagermitarbeiter',
            'logistik': 'Logistiker',
            'elektrotechnik': 'Elektrotechniker',
            'maschinenbau': 'Maschinenbauingenieur',
            'it': 'IT-Fachkraft',
        }
        
        text_lower = text.lower()
        
        # Check for matches (longest first to catch "hardwarekonstruktion" before "konstruktion")
        for keyword in sorted(POSITION_KEYWORDS.keys(), key=len, reverse=True):
            if keyword in text_lower:
                return POSITION_KEYWORDS[keyword]
        
        return None
    
    def _build_resume_extraction_prompt(self) -> str:
        """Build system prompt for resume extraction."""
        return """Du bist ein Experte für die Extraktion von strukturierten Lebenslaufdaten aus Bewerbungsgesprächen.

AUFGABE:
Extrahiere aus dem deutschen Transkript alle relevanten Lebenslaufdaten und gib sie als strukturiertes JSON zurück.

═══════════════════════════════════════════════════════════════════
BERUFSBEZEICHNUNG EXTRAHIEREN (HÖCHSTE PRIORITÄT!)
═══════════════════════════════════════════════════════════════════

🚨 KRITISCH: Für JEDE berufliche Station MUSS das "position"-Feld mit der KONKRETEN Berufsbezeichnung gefüllt werden!

Der Agent fragt im Gespräch DIREKT nach Berufsbezeichnungen/Positionen:
- "Was haben Sie gelernt?" / "Was haben Sie denn gelernt?"
- "Was für Tätigkeiten haben Sie?" / "Was machen Sie beruflich?"
- "Als was arbeiten Sie?" / "Welche Position haben Sie?"
- "Wo waren Sie dort?" / "Was haben Sie da gemacht?"

⚠️ Die Antwort des Kandidaten ist die POSITION - übernehme sie EXAKT!

✅ BEISPIELE KORREKTE EXTRAKTION:
┌────────────────────────────────────────────────────────────────┐
│ Agent: "Was haben Sie denn gelernt?"                           │
│ Kandidat: "Ich bin staatlich anerkannte Erzieherin"           │
│ → position: "Staatlich anerkannte Erzieherin" ✅               │
│                                                                 │
│ Agent: "Was für Tätigkeiten haben Sie?"                        │
│ Kandidat: "Ich bin in der Hardwarekonstruktion tätig"         │
│ → position: "Hardwarekonstrukteur" ✅                          │
│                                                                 │
│ Agent: "Wo waren Sie dort?"                                    │
│ Kandidat: "Da war ich Kita-Leitung"                           │
│ → position: "Kita-Leitung" ✅                                  │
│                                                                 │
│ Kandidat: "Ich arbeite als stellvertretende Kita-Leitung"     │
│ → position: "Stellvertretende Kita-Leitung" ✅                │
│                                                                 │
│ Kandidat: "Ich bin Pflegefachmann"                            │
│ → position: "Pflegefachmann" ✅                                │
└────────────────────────────────────────────────────────────────┘

✅ UMFORMUNGEN BEI VAGEN ANGABEN:
- "Ich bin in der Konstruktion tätig" → position: "Konstrukteur"
- "Ich arbeite in der Pflege" → position: "Pflegefachkraft"
- "Ich bin in der IT" → position: "IT-Fachkraft"
- "Ich mache Buchhaltung" → position: "Buchhalter"

❌ NIEMALS vage Positionen wie:
- "Arbeit in der Konstruktion" ❌
- "Tätig in der Pflege" ❌
- "Mitarbeiter bei Firma X" ❌
- "Beschäftigt im Bereich IT" ❌

🚨 REGEL: position ist ein PFLICHTFELD - JEDE Experience braucht eine konkrete Berufsbezeichnung!

═══════════════════════════════════════════════════════════════════
PERSÖNLICHE DATEN - WOHNORT & POSTLEITZAHL (KRITISCH!)
═══════════════════════════════════════════════════════════════════

⚠️ POSTLEITZAHL (PLZ) EXTRAHIEREN - 5 STELLEN (HÖCHSTE PRIORITÄT!):

🚨 KRITISCH: PLZ ist ein PFLICHTFELD! Durchsuche das GESAMTE Transkript gründlich!
🚨 Lies JEDE Zeile sorgfältig - PLZ kann überall im Gespräch erwähnt werden!
🚨 BESONDERS WICHTIG: PLZ wird oft AM ENDE des Gesprächs gefragt!
🚨 Überfliege NICHT die letzten 5-10 Zeilen - dort steht oft die PLZ!
🚨 Bei Unsicherheit: Lies nochmal! PLZ ist oft versteckt in längeren Sätzen!

✅ ERKENNUNGSMUSTER:
┌────────────────────────────────────────────────────────────────┐
│ ANFANG DES GESPRÄCHS:                                          │
│ "Ich wohne in Berlin, Postleitzahl 10115"                     │
│ → postal_code: "10115", city: "Berlin"                        │
│                                                                 │
│ MITTE DES GESPRÄCHS:                                           │
│ "In der 12345 Musterstraße wohne ich"                         │
│ → postal_code: "12345", city: null                            │
│                                                                 │
│ ENDE DES GESPRÄCHS (HÄUFIG!):                                 │
│ Recruiter: "Wo wohnen Sie denn?"                              │
│ Kandidat: "In 90402 Nürnberg"                                 │
│ → postal_code: "90402", city: "Nürnberg"                      │
│                                                                 │
│ ENDE DES GESPRÄCHS (HÄUFIG!):                                 │
│ Recruiter: "Können Sie mir noch Ihre PLZ nennen?"             │
│ Kandidat: "Ja klar, 49536"                                    │
│ → postal_code: "49536", city: null                            │
│                                                                 │
│ ENDE DES GESPRÄCHS (HÄUFIG!):                                 │
│ Recruiter: "In welcher Stadt wohnen Sie?"                     │
│ Kandidat: "In Lotte, das ist 49536"                           │
│ → postal_code: "49536", city: "Lotte"                         │
│                                                                 │
│ "Ich bin aus München, PLZ 80331"                              │
│ → postal_code: "80331", city: "München"                       │
│                                                                 │
│ "Ich wohne ganz in der Nähe, in 90402 Nürnberg"              │
│ → postal_code: "90402", city: "Nürnberg"                      │
│                                                                 │
│ "Aus dem 49536 Lotte komme ich"                               │
│ → postal_code: "49536", city: "Lotte"                         │
│                                                                 │
│ "Ich wohne in 10178 Berlin-Mitte"                             │
│ → postal_code: "10178", city: "Berlin"                        │
└────────────────────────────────────────────────────────────────┘

✅ KONTEXT-KEYWORDS (helfen bei der Identifikation):
- "wohne in", "wohne ganz in der Nähe"
- "aus [Stadt]", "komme aus", "bin aus"
- "PLZ", "Postleitzahl"
- Stadtnamen (Berlin, München, Hamburg, etc.)
- "in [PLZ] [Stadt]" oder "[Stadt] [PLZ]"

✅ REGELN (STRENG BEFOLGEN!):
1. 🚨 PLZ ist IMMER 5 Ziffern (keine 4 oder 6!)
2. 🚨 PLZ steht meist VOR oder NACH dem Stadtnamen
3. 🚨 Bei mehreren 5-stelligen Zahlen: Nimm die mit Wohnort-Kontext
4. 🚨 Deutsche PLZ-Bereiche: 01xxx-99xxx (prüfe ob gültig!)
5. 🚨 Durchsuche GESAMTES Transkript - PLZ kann am Anfang, Mitte oder Ende erwähnt werden!
6. 🚨 Achte auf indirekte Erwähnungen: "da wo ich wohne, in der 12345", "bei mir in 67890"
7. 🚨 NUR wenn wirklich keine PLZ im Transkript: null (aber erst nach GRÜNDLICHER Suche!)

❌ KEINE Postleitzahl (häufige Fehlerquellen):
- Telefonnummern (länger als 5 Ziffern, oft mit +49)
- Hausnummern (stehen NACH Straßenname, z.B. "Musterstraße 123")
- Jahreszahlen (1900-2026, meist im Kontext "seit 2020")
- Personalnummern oder IDs
- Zahlen ohne Wohnort-Kontext

⚠️ CITY EXTRAHIEREN:
- Extrahiere den Stadtnamen/Ort wenn erwähnt
- Format: "Berlin" (nicht "Berlin-Mitte" oder "in Berlin")
- Auch kleine Städte/Gemeinden zählen (z.B. "Lotte", "Lengrich")
- Bei Stadtteilen: Nur Hauptstadt (z.B. "Berlin-Kreuzberg" → "Berlin")

BEISPIELE (KRITISCH - LERNE AUS DIESEN!):
┌────────────────────────────────────────────────────────────────┐
│ Transkript: "Ich bin 35 Jahre alt und wohne in 90402 Nürnberg"│
│             ^^^^^^^^                           ^^^^^           │
│             KEIN PLZ!                          PLZ! ✅          │
│                                                                 │
│ Output: postal_code: "90402", city: "Nürnberg"                │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ Transkript: "Musterstraße 12345 in Hamburg"                   │
│                        ^^^^^                                    │
│                        Hausnummer, KEIN PLZ! ❌                │
│                                                                 │
│ Transkript: "...und wohne in 20095 Hamburg"                   │
│                              ^^^^^                              │
│                              PLZ! ✅                            │
│                                                                 │
│ Output: postal_code: "20095", city: "Hamburg"                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ Transkript: "Seit 2019 arbeite ich hier, wohne in 10115"     │
│            ^^^^^                                  ^^^^^        │
│            Jahr, KEIN PLZ!                        PLZ! ✅      │
│                                                                 │
│ Output: postal_code: "10115", city: null                      │
└────────────────────────────────────────────────────────────────┘

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

3. POSITION-FELD (KRITISCH - ABSOLUTES PFLICHTFELD!):
   
   🚨 KRITISCH: JEDE Experience MUSS eine konkrete Berufsbezeichnung im "position"-Feld haben!
   🚨 NIEMALS eine Experience ohne "position" senden - das führt zu Datenverlust!
   🚨 "position" ist das WICHTIGSTE Feld - es definiert WAS der Kandidat gemacht hat!
   
   ✅ GUTE Berufsbezeichnungen (konkret & präzise):
   ┌────────────────────────────────────────────────────────────────┐
   │ ✅ "Konstrukteur"                                              │
   │ ✅ "Werkstudent Hardwarekonstruktion"                          │
   │ ✅ "Projektleiter Elektrotechnik"                              │
   │ ✅ "Pflegefachkraft Intensivstation"                           │
   │ ✅ "Software-Entwickler Backend"                               │
   │ ✅ "Gesundheits- und Krankenpfleger"                           │
   │ ✅ "Ingenieur Automatisierungstechnik"                         │
   │ ✅ "Teamleiter Vertrieb"                                       │
   └────────────────────────────────────────────────────────────────┘
   
   ❌ SCHLECHTE Bezeichnungen (vage, zu allgemein):
   ┌────────────────────────────────────────────────────────────────┐
   │ ❌ "Arbeit in der Konstruktion" → ZU VAGE!                     │
   │ ❌ "tätig in der Pflege" → ZU VAGE!                            │
   │ ❌ "im Bereich IT" → ZU VAGE!                                  │
   │ ❌ "Mitarbeiter" → ZU ALLGEMEIN!                               │
   │ ❌ "Beschäftigt bei Firma X" → KEINE BERUFSBEZEICHNUNG!        │
   └────────────────────────────────────────────────────────────────┘
   
   🎯 EXTRAKTIONSREGELN:
   1. Höre auf die GENAUE Berufsbezeichnung die der Kandidat nennt
   2. Format: "[Berufsbezeichnung] [optional: Spezialisierung]"
   3. Bei Werkstudenten: "Werkstudent [Bereich]" (z.B. "Werkstudent IT")
   4. Bei dualen Studenten: "Dual Student [Bereich]" (z.B. "Dual Student Elektrotechnik")
   5. Bei Praktikanten: "Praktikant [Bereich]" (z.B. "Praktikant Marketing")
   6. Wenn nur Bereich erwähnt: Leite sinnvolle Berufsbezeichnung ab
      Beispiel: "in der Pflege gearbeitet" → "Pflegekraft" (nicht "Arbeit in der Pflege")
   
   ⚠️ FALLBACK (NUR wenn wirklich keine Berufsbezeichnung erkennbar):
   - Nutze employment_type + Firma: "Mitarbeiter bei [Firma]"
   - ABER: Das ist die LETZTE Option! Versuche immer, eine konkrete Berufsbezeichnung zu finden!

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

4. DEUTSCHE ANERKENNUNG AUSLÄNDISCHER ABSCHLÜSSE (NEU - KRITISCH!):
   
   ⚠️ WENN AUSLÄNDISCHE AUSBILDUNG MIT DEUTSCHER ANERKENNUNG ERWÄHNT:
   → Erstelle 2 SEPARATE Education-Einträge!
   
   ✅ ERKENNUNGSMUSTER (Keywords für Anerkennung):
   - "deutsche Anerkennung", "anerkannt in Deutschland"
   - "Gleichwertigkeitsbescheinigung", "Gleichwertigkeitsprüfung"
   - "Anerkennung vom [Behörde]", "anerkannt durch [Behörde]"
   - "Anerkennung beantragt", "Anerkennungsverfahren läuft"
   - Behörden: Regierungspräsidium, IHK, Kultusministerium, ZAB, etc.
   
   ✅ RICHTIG - 2 Separate Einträge:
   ┌────────────────────────────────────────────────────────────────┐
   │ Transkript:                                                     │
   │ "Ich habe 2018 in der Türkei meine Ausbildung als Pflege-     │
   │  fachmann gemacht und 2023 die deutsche Anerkennung vom        │
   │  Regierungspräsidium Stuttgart bekommen."                      │
   │                                                                 │
   │ Output - Education 1 (Originalabschluss):                      │
   │ {                                                               │
   │   "end": "2018-12-31",                                         │
   │   "company": "Pflegeschule [Stadt], Türkei",                   │
   │   "description": "Ausbildung Pflegefachmann"                   │
   │ }                                                               │
   │                                                                 │
   │ Output - Education 2 (Deutsche Anerkennung):                   │
   │ {                                                               │
   │   "end": "2023-12-31",                                         │
   │   "company": "Regierungspräsidium Stuttgart",                  │
   │   "description": "Deutsche Anerkennung: Pflegefachmann (gleichwertig)"│
   │ }                                                               │
   └────────────────────────────────────────────────────────────────┘
   
   ✅ DESCRIPTION-FORMAT für Anerkennung:
   - "Deutsche Anerkennung: [Originalabschluss] ([Status])"
   - Status: "gleichwertig", "vollständig anerkannt", "teilweise anerkannt"
   - Bei laufendem Verfahren: "Deutsche Anerkennung: [Abschluss] (beantragt)"
   
   ✅ COMPANY für Anerkennung:
   - Name der anerkennenden Behörde/Institution
   - Regierungspräsidium [Stadt] (z.B. "Regierungspräsidium Stuttgart")
   - IHK [Stadt] (z.B. "IHK Nürnberg")
   - Kultusministerium [Bundesland]
   - ZAB (Zentralstelle für ausländisches Bildungswesen)
   - Bei unklarer Behörde: "Anerkennungsstelle Deutschland"
   
   ✅ WEITERE BEISPIELE:
   
   Beispiel 1 - Ausbildung mit Anerkennung:
   ┌────────────────────────────────────────────────────────────────┐
   │ "Krankenpfleger hab ich in Polen gelernt, 2015 abgeschlossen. │
   │  Die Anerkennung von der IHK Berlin hab ich 2020 bekommen."   │
   │                                                                 │
   │ → 2 Einträge:                                                   │
   │   1. "Ausbildung Krankenpfleger" (Polen, 2015)                 │
   │   2. "Deutsche Anerkennung: Krankenpfleger (anerkannt)" (IHK, 2020)│
   └────────────────────────────────────────────────────────────────┘
   
   Beispiel 2 - Studium mit Anerkennung:
   ┌────────────────────────────────────────────────────────────────┐
   │ "Ich habe in Indien Elektrotechnik studiert, Bachelor 2019.   │
   │  Vom Kultusministerium Bayern wurde das 2021 als gleichwertig │
   │  mit dem deutschen Bachelor anerkannt."                        │
   │                                                                 │
   │ → 2 Einträge:                                                   │
   │   1. "Bachelor Elektrotechnik" (Indien, 2019)                  │
   │   2. "Deutsche Anerkennung: Bachelor Elektrotechnik (gleichwertig)"│
   │      (Kultusministerium Bayern, 2021)                          │
   └────────────────────────────────────────────────────────────────┘
   
   Beispiel 3 - Anerkennung beantragt (läuft noch):
   ┌────────────────────────────────────────────────────────────────┐
   │ "Mein Abschluss aus Syrien ist noch nicht anerkannt, aber ich │
   │  habe es beantragt beim Regierungspräsidium."                 │
   │                                                                 │
   │ → 2 Einträge:                                                   │
   │   1. "[Abschluss]" (Syrien, [Jahr])                            │
   │   2. "Deutsche Anerkennung: [Abschluss] (beantragt)"           │
   │      (Regierungspräsidium [Stadt], [Antragsjahr])              │
   └────────────────────────────────────────────────────────────────┘
   
   ❌ FALSCH - nur 1 Eintrag mit Note:
   {
     "description": "Pflegefachmann (Türkei, anerkannt)"  ← ZU VAGE!
   }
   
   ✅ WICHTIGE REGELN:
   1. IMMER 2 separate Einträge bei erwähnter Anerkennung
   2. Chronologisch korrekt (Original zuerst, dann Anerkennung)
   3. Behördenname VOLLSTÄNDIG in company-Feld
   4. Status in description-Klammern angeben
   5. Auch bei "beantragt" oder "läuft noch" → 2 Einträge!

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
1. ✅ PLZ extrahiert? (HÖCHSTE PRIORITÄT - Transkript nochmal durchlesen!)
2. ✅ JEDE Experience hat "position"-Feld mit konkreter Berufsbezeichnung? (KRITISCH!)
3. ✅ JEDE Experience mit mind. 100 Zeichen in tasks? (KRITISCH!)
4. ✅ JEDE Experience hat vollständigen Firmennamen in company? (KRITISCH!)
5. ✅ Alle Daten temporal gültig? (start < end)
6. ✅ Alle erwähnten Jobs erfasst?
7. ✅ Alle erwähnten Bildungsstationen erfasst (inkl. Schule!)? (KRITISCH!)
8. ✅ Ausländische Abschlüsse MIT deutscher Anerkennung → 2 separate Einträge? (NEU!)
9. ✅ Wenn "current_job" → muss Experience mit end=null existieren
10. ✅ Keine Halluzinationen? (nur Transkript-Fakten)
11. ✅ Bei Teilzeit: Stundenzahl angegeben? (KRITISCH!)

🚨 DOPPELT PRÜFEN (BEVOR DU ANTWORTEST):
   - Ist "postal_code" ausgefüllt? (Wenn ja → GUT! Wenn nein → NOCHMAL SUCHEN!)
   - Hat JEDE Experience ein "position"-Feld? (Zähle nach: experiences.length == positions.length?)
   - Sind alle "position"-Werte konkrete Berufsbezeichnungen? (Keine "Arbeit in..." oder "tätig als..."!)

🚨 ABLEHNUNGSGRÜNDE (DIESE FEHLER FÜHREN ZU DATENVERLUST!):
- ❌ Experiences OHNE "position"-Feld werden KOMPLETT GELÖSCHT! (KRITISCH!)
- ❌ Experiences mit vager "position" (z.B. "Arbeit in...") werden ABGELEHNT!
- ❌ Experiences mit tasks < 100 Zeichen werden ABGELEHNT!
- ❌ Tasks mit "- " am Anfang werden ABGELEHNT (nutze Semikolon-Format)!
- ❌ Vage Firmennamen ("eine Firma") werden ABGELEHNT!
- ❌ Ausländische Abschlüsse MIT Anerkennung als 1 Eintrag werden ABGELEHNT (braucht 2!)!
- ⚠️ Fehlende PLZ führt zu unvollständigem Bewerberprofil!

💡 QUALITÄTSZIEL:
   - 100% der Experiences haben konkrete "position"
   - 100% der Tasks haben mind. 100 Zeichen
   - PLZ ist extrahiert (wenn im Transkript erwähnt)

═══════════════════════════════════════════════════════════════════
OUTPUT JSON SCHEMA
═══════════════════════════════════════════════════════════════════

{
  "postal_code": string|null (5-stellige PLZ, z.B. "10115", "90402" - NUR wenn im Transkript erwähnt!),
  "city": string|null (Stadt/Ort, z.B. "Berlin", "München", "Lotte" - NUR wenn im Transkript erwähnt!),
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
      "position": string (🚨🚨🚨 ABSOLUTES PFLICHTFELD - KOMMT ZUERST! 🚨🚨🚨
                          Konkrete Berufsbezeichnung, die der Kandidat nennt!
                          Beispiele: "Konstrukteur", "Staatlich anerkannte Erzieherin", 
                          "Kita-Leitung", "Pflegefachmann", "Werkstudent Hardwarekonstruktion"
                          NIEMALS vage wie "Arbeit in..." oder "tätig als..."!),
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

KRITISCHE REGELN (AUSNAHMSLOS BEFOLGEN!):
❌ KEINE Erfindungen - nur Transkript-Fakten
❌ KEINE "- " am Anfang von tasks (nutze Semikolon-Format)
❌ KEINE vagen tasks-Beschreibungen (<100 Zeichen)
❌ KEINE vagen Firmennamen ("eine Firma", "ein Unternehmen")
❌ KEINE fehlenden Schulen/Unis wenn im Transkript erwähnt
❌ KEINE fehlenden Stundenzahlen bei Teilzeit
🚨 NIEMALS Experience OHNE "position"-Feld senden - das ist DATENVERLUST!
🚨 NIEMALS vage "position" wie "Arbeit in..." - das wird ABGELEHNT!
🚨 PLZ MUSS gesucht werden - lies GESAMTES Transkript durch!

✅ Bei Unsicherheit bei company: null verwenden (aber nur wenn wirklich unklar!)
✅ Bei Unsicherheit bei position: Leite aus Kontext ab (z.B. "Pflegekraft" statt "in der Pflege")
✅ Temporale Annotationen [≈Jahr] nutzen
✅ JEDE Experience detailliert beschreiben mit erkennbarem Schwerpunkt
✅ Position IMMER als konkrete Berufsbezeichnung (niemals "Arbeit in...", "tätig als...")
✅ Hauptjob vs Nebenjob durch employment_type unterscheiden
✅ PLZ gründlich suchen - am Anfang, Mitte UND Ende des Transkripts!
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
        
        context += f"\n\n🚨 WICHTIG: Das Transkript hat {len(transcript)} Zeilen."
        context += "\n🚨 PLZ wird oft AM ENDE des Gesprächs erwähnt - lies ALLE Zeilen gründlich!"
        context += "\n🚨 Überfliege nicht das Ende - dort stehen oft wichtige Infos (PLZ, Startdatum, etc.)!"
        context += "\n\nExtrahiere nun die strukturierten Lebenslaufdaten als JSON:"
        
        return context



















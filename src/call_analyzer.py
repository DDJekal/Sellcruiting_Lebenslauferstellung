"""LLM-based call quality analyzer for recruiting conversations."""
import json
import logging
from typing import Dict, Any, List, Optional

from llm_client import LLMClient

logger = logging.getLogger(__name__)


# 8 Phasen des Recruiting-Gesprächs
CONVERSATION_PHASES = {
    1: "Begrüßung & DSGVO",
    2: "Motivation & Erwartung",
    3: "Arbeitgebervorstellung",
    4: "Präferenzen & Rahmenbedingungen",
    5: "Ausbildung & Qualifikation",
    6: "Beruflicher Werdegang",
    7: "Präzisierung",
    8: "Orga & Abschluss",
}

# Fehler-Kategorien
ERROR_CATEGORIES = [
    "verstaendnis",     # Agent versteht Antwort falsch
    "tempo",            # Zu schnell, Bewerber kann nicht folgen
    "kettenfragen",     # Mehrere Fragen pro Redeanteil
    "wiederholung",     # Bereits beantwortete Frage nochmal gestellt
    "formulierung",     # Zu komplex, Bewerber versteht nicht
    "empathie",         # Kein Eingehen auf Unsicherheit
    "ablehnung",        # Agent lehnt Bewerber ab (VERBOTEN)
    "phasenbruch",      # Phasen-Reihenfolge verletzt
    "unterbrechung",    # Agent unterbricht Bewerber
    "doppelfrage",      # Duplikat-Check ignoriert
]

ANALYSIS_SYSTEM_PROMPT = """Du bist ein Gesprächsqualitäts-Analyst für KI-gestützte Recruiting-Telefonate.

Das Gespräch folgt 8 Phasen:
1. Begrüßung & DSGVO – Kurze Begrüßung, Zeit prüfen, Datenschutz-Einwilligung
2. Motivation & Erwartung – Offene Fragen zu Beweggründen, Sprachkenntnisse (Pflicht)
3. Arbeitgebervorstellung (optional) – 3-4 Sätze über das Unternehmen
4. Präferenzen & Rahmenbedingungen – Vorstellungen zum Arbeitsalltag
5. Ausbildung & Qualifikation – Schulabschluss, Ausbildung, Institution, Zeiträume
6. Beruflicher Werdegang – Max. 3 Stationen antichronologisch
7. Präzisierung (optional) – Vage Angaben klären
8. Orga & Abschluss – Stellenumfang, Starttermin, Erreichbarkeit, PLZ, Verabschiedung

AGENT-REGELN (Verstöße erkennen):
- Eine Frage pro Redeanteil, keine Kettenfragen
- Bereits Beantwortetes überspringen (Duplikat-Check)
- Bei Unterbrechung: aussprechen lassen, darauf eingehen, dann weiter
- Keine Ablehnung des Bewerbers, NIEMALS
- Max. 2-3 Beispiele nennen, keine Listen vorlesen
- Zeitangaben: Monat + Jahr nachfragen wenn nur Jahr genannt
- PLZ Ziffer für Ziffer sprechen
- Keine Telefonnummer oder E-Mail aktiv erfragen (sollen bereits vorliegen)
- Kein Smalltalk nach Verabschiedung
- Gespräch IMMER bis Phase 8 führen, unabhängig von Passung

FEHLER-KATEGORIEN:
- verstaendnis: Agent versteht Antwort falsch oder interpretiert sie falsch
- tempo: Agent spricht zu schnell, Bewerber kann nicht folgen
- kettenfragen: Mehrere Fragen in einem Redeanteil
- wiederholung: Bereits beantwortete Frage erneut gestellt
- formulierung: Frage zu komplex oder unklar für den Bewerber
- empathie: Kein Eingehen auf Unsicherheit oder Frustration des Bewerbers
- ablehnung: Agent lehnt Bewerber ab oder bewertet negativ (VERBOTEN)
- phasenbruch: Phasen-Reihenfolge nicht eingehalten
- unterbrechung: Agent unterbricht den Bewerber
- doppelfrage: Duplikat-Check ignoriert (z.B. Sprachkenntnisse oder PLZ doppelt gefragt)

SENTIMENT-SKALA (1-10):
1-3: Negativ (frustriert, genervt, verwirrt)
4-5: Leicht negativ (unsicher, zurückhaltend)
6-7: Neutral bis leicht positiv
8-10: Positiv (engagiert, offen, freundlich)

ENGAGEMENT-BEWERTUNG:
- Kurze Antworten ("ja", "nein") = niedrig
- Detaillierte Antworten = hoch
- Rückfragen = sehr hoch
- "Hallo?" / "Wie bitte?" = Verständnisprobleme
- Einsilbige Antworten nach langer Frage = Desinteresse oder Überforderung

Analysiere das Transkript und gib AUSSCHLIESSLICH folgendes JSON zurück (keine Erklärung davor oder danach):

{
  "quality_score": <1-10>,
  "hangup_phase": <1-8 oder null>,
  "hangup_phase_name": "<Phasenname oder null>",
  "last_completed_phase": <1-8>,
  "phases_completed": ["Phase 1 Name", "Phase 2 Name", ...],
  "phases_missing": ["Phase X Name", ...],
  "hangup_reason": "<Vermuteter Grund für Abbruch oder null>",
  "hangup_trigger_moment": "<Zeitpunkt/Kontext des Abbruchs oder null>",
  "hangup_category": "<Fehler-Kategorie oder null>",
  "hangup_severity": <1-10 oder null>,
  "sentiment_flow": [
    {"phase": 1, "name": "Begrüßung & DSGVO", "score": <1-10>},
    {"phase": 2, "name": "Motivation & Erwartung", "score": <1-10>}
  ],
  "sentiment_trend": "<stabil|abfallend|ansteigend|wechselnd>",
  "sentiment_turning_point": <Phase-Nummer wo Stimmung kippt oder null>,
  "engagement_score": <1-10>,
  "avg_response_length": "<kurz|mittel|ausfuehrlich>",
  "signs_of_disinterest": ["Beschreibung 1", ...],
  "signs_of_confusion": ["Beschreibung 1", ...],
  "agent_errors": [
    {
      "category": "<Fehler-Kategorie>",
      "description": "<Was ist passiert>",
      "severity": <1-10>,
      "phase": <1-8>,
      "context": "<Kontext aus dem Transkript>"
    }
  ],
  "top_error_category": "<häufigste Fehler-Kategorie oder null>",
  "rule_violations": [
    {
      "rule": "<Welche Regel verletzt>",
      "description": "<Was ist passiert>",
      "severity": <1-10>,
      "phase": <1-8>
    }
  ],
  "completeness_score": <1-10>,
  "questions_asked": <Anzahl>,
  "questions_expected": <Anzahl basierend auf den Phasen>,
  "missing_topics": ["Thema 1", ...],
  "vague_answers": [
    {"topic": "<Thema>", "answer_given": "<Was gesagt wurde>", "precision": "<vague|unclear|partial>"}
  ],
  "analysis_summary": "<2-3 Sätze Zusammenfassung>",
  "improvement_suggestions": ["Vorschlag 1", "Vorschlag 2", ...]
}"""


class CallAnalyzer:
    """Analyze recruiting call quality using LLM."""
    
    def __init__(self):
        """Initialize with LLM client (Claude preferred)."""
        self.llm_client = LLMClient(prefer_claude=True)
    
    def analyze(
        self,
        transcript: List[Dict[str, str]],
        metadata: Dict[str, Any],
        trigger: str = "hangup"
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a call transcript for quality issues.
        
        Args:
            transcript: List of {"speaker": "A"|"B", "text": "..."}
            metadata: ElevenLabs metadata dict
            trigger: "hangup" (Bewerber hat aufgelegt) or "long_call" (>8 min)
            
        Returns:
            Analysis result dict or None if analysis fails
        """
        if not transcript or len(transcript) < 2:
            logger.warning("[ANALYZER] Transcript too short for analysis")
            return None
        
        try:
            # Build user prompt
            user_prompt = self._build_user_prompt(transcript, metadata, trigger)
            
            # Call LLM
            logger.info(f"[ANALYZER] Starting {trigger} analysis...")
            response_text = self.llm_client.create_completion(
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=4000
            )
            
            # Parse JSON
            result = json.loads(response_text)
            
            # Add computed fields
            result["error_count"] = len(result.get("agent_errors", []))
            result["rule_violation_count"] = len(result.get("rule_violations", []))
            
            # Serialize nested objects to JSON strings for DB storage
            result = self._serialize_for_db(result)
            
            logger.info(f"[ANALYZER] Analysis complete: quality={result.get('quality_score')}/10, errors={result.get('error_count')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"[ANALYZER] JSON parsing error: {e}")
            return None
        except Exception as e:
            logger.error(f"[ANALYZER] Analysis failed: {e}", exc_info=True)
            return None
    
    def _build_user_prompt(
        self,
        transcript: List[Dict[str, str]],
        metadata: Dict[str, Any],
        trigger: str
    ) -> str:
        """Build the user prompt for the analysis LLM."""
        
        # Format transcript
        transcript_text = ""
        for i, turn in enumerate(transcript):
            speaker = "Bewerber" if turn["speaker"] == "A" else "Agent"
            transcript_text += f"[{i+1}] {speaker}: {turn['text']}\n"
        
        # Trigger context
        if trigger == "hangup":
            trigger_context = (
                "ANALYSE-ANLASS: Der Bewerber hat das Gespräch vorzeitig beendet (aufgelegt).\n"
                "FOKUS: Analysiere besonders WARUM der Bewerber aufgelegt hat und in welcher Phase.\n"
                "Achte auf Anzeichen von Frustration, Verwirrung oder Desinteresse VOR dem Abbruch."
            )
        else:
            trigger_context = (
                "ANALYSE-ANLASS: Das Gespräch war ungewöhnlich lang (>8 Minuten).\n"
                "FOKUS: Analysiere besonders welche Phasen zu lang gedauert haben und warum.\n"
                "Achte auf unnötige Wiederholungen, Verständnisprobleme oder ineffiziente Gesprächsführung."
            )
        
        # Metadata context
        duration_mins = metadata.get("call_duration_secs", 0) / 60 if metadata.get("call_duration_secs") else 0
        meta_context = f"""CALL-METADATEN:
- Dauer: {duration_mins:.1f} Minuten
- Beendigungsgrund: {metadata.get('termination_reason', 'unbekannt')}
- Unternehmen: {metadata.get('company_name', 'unbekannt')}
- Stelle: {metadata.get('campaign_role_title', 'unbekannt')}"""
        
        return f"""{trigger_context}

{meta_context}

TRANSKRIPT:
{transcript_text}

Analysiere dieses Gespräch und gib das JSON-Ergebnis zurück."""
    
    def _serialize_for_db(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Convert nested objects to JSON strings for database storage."""
        json_fields = [
            "sentiment_flow", "signs_of_disinterest", "signs_of_confusion",
            "agent_errors", "rule_violations", "missing_topics",
            "vague_answers", "improvement_suggestions",
            "phases_completed", "phases_missing"
        ]
        
        serialized = {}
        for key, value in result.items():
            if key in json_fields and isinstance(value, (list, dict)):
                serialized[key] = json.dumps(value, ensure_ascii=False)
            else:
                serialized[key] = value
        
        return serialized

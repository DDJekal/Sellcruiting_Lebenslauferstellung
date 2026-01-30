"""Type enricher for inferring prompt types (Shadow-Types)."""
import re
import json
import hashlib
from typing import Dict, List, Any
import os

from models import ShadowType, PromptType, MandantenConfig
from llm_client import LLMClient


class TypeEnricher:
    """Infers prompt types using heuristics + LLM fallback."""
    
    def __init__(self, api_key: str = None, prefer_claude: bool = True):
        """
        Initialize type enricher.
        
        Args:
            api_key: Deprecated (uses env vars now)
            prefer_claude: Use Claude for type classification (default: True, Claude erkennt Typen besser)
        """
        self.llm_client = LLMClient(prefer_claude=prefer_claude)
        self.cache: Dict[str, ShadowType] = {}
    
    def infer_types(self, protocol: Dict[str, Any], mandanten_config: MandantenConfig) -> Dict[int, ShadowType]:
        """Infer types for all prompts in protocol."""
        shadow_types = {}
        unsure_prompts = []
        
        for page in protocol["pages"]:
            page_name = page["name"]
            
            for prompt in page["prompts"]:
                # Check if explicit type exists in protocol (NEW)
                explicit_type = prompt.get("type")
                if explicit_type:
                    try:
                        prompt_type = PromptType(explicit_type)
                        shadow_types[prompt["id"]] = ShadowType(
                            prompt_id=prompt["id"],
                            inferred_type=prompt_type,
                            confidence=1.0,
                            reasoning=f"Explicit type from protocol: {explicit_type}"
                        )
                        continue  # Skip heuristics and LLM
                    except ValueError:
                        # Invalid type value, fall back to heuristics
                        pass
                
                # Check cache first
                cache_key = self._get_cache_key(prompt)
                if cache_key in self.cache:
                    shadow_types[prompt["id"]] = self.cache[cache_key]
                    continue
                
                # Try heuristics
                heuristic_result = self._apply_heuristics(
                    prompt, page_name, mandanten_config
                )
                
                if heuristic_result and heuristic_result.confidence >= 0.9:
                    shadow_types[prompt["id"]] = heuristic_result
                    self.cache[cache_key] = heuristic_result
                else:
                    # Mark for LLM classification
                    unsure_prompts.append((prompt, page_name))
        
        # Batch classify unsure prompts via LLM
        if unsure_prompts:
            llm_results = self._llm_classify_batch(unsure_prompts)
            for prompt_id, shadow_type in llm_results.items():
                shadow_types[prompt_id] = shadow_type
                # Cache it
                cache_key = self._get_cache_key({"id": prompt_id, "question": shadow_type.reasoning})
                self.cache[cache_key] = shadow_type
        
        return shadow_types
    
    def _get_cache_key(self, prompt: Dict[str, Any]) -> str:
        """Generate cache key for prompt."""
        text = f"{prompt['id']}_{prompt['question']}"
        return hashlib.md5(text.encode()).hexdigest()
    
    def _apply_heuristics(
        self,
        prompt: Dict[str, Any],
        page_name: str,
        mandanten_config: MandantenConfig
    ) -> ShadowType:
        """Apply heuristic rules to infer prompt type."""
        question = prompt["question"]
        q_lower = question.lower()
        
        # Page-based fallback (info pages)
        if page_name in mandanten_config.info_page_names:
            if "!!!" in question or "bitte unbedingt erwähnen" in q_lower:
                return ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=PromptType.RECRUITER_INSTRUCTION,
                    confidence=0.98,
                    reasoning="Recruiter instruction (contains !!!)"
                )
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.INFO,
                confidence=0.94,
                reasoning="Info page"
            )
        
        # Mandanten-specific heuristics
        for rule in mandanten_config.heuristic_rules:
            if re.search(rule.pattern, q_lower, re.IGNORECASE):
                return ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=rule.type,
                    confidence=rule.confidence,
                    reasoning=f"Matched pattern: {rule.pattern}"
                )
        
        # General heuristics
        
        # 1. AUSWAHLFRAGEN: "Station: A, B, C, D" oder "Schicht: X, Y, Z"
        # Pattern: "Begriff: Option1, Option2, Option3"
        if re.search(r':\s*[\w\säüöÄÜÖß\-]+,\s*[\w\säüöÄÜÖß\-]+,', question):
            # Zähle Kommas - wenn >= 2, dann sind es mehrere Optionen
            comma_count = question.count(',')
            if comma_count >= 2:
                return ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=PromptType.TEXT,  # oder TEXT_LIST wenn Mehrfachauswahl möglich
                    confidence=0.94,
                    reasoning=f"Auswahlfrage mit {comma_count+1} Optionen (Format: 'X: A, B, C')"
                )
        
        # 2. ARBEITSZEITFRAGEN: "Vollzeit: X Std" oder "Teilzeit"
        if re.search(r'(vollzeit|teilzeit).*:.*\d+.*std', q_lower):
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.YES_NO_WITH_DETAILS,
                confidence=0.93,
                reasoning="Arbeitszeitfrage mit Stundenzahl"
            )
        
        if re.search(r'(vollzeit|teilzeit).*:', q_lower):
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.YES_NO,
                confidence=0.91,
                reasoning="Arbeitszeitfrage"
            )
        
        # 3. STANDARD: "Zwingend:" oder "Wünschenswert:"
        if q_lower.startswith("zwingend:") or q_lower.startswith("wünschenswert:"):
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.YES_NO,
                confidence=0.92,
                reasoning="Starts with 'Zwingend:' or 'Wünschenswert:'"
            )
        
        # If no heuristic matched
        return None
    
    def _llm_classify_batch(
        self, prompts_with_pages: List[tuple]
    ) -> Dict[int, ShadowType]:
        """Classify prompts using LLM (batch)."""
        results = {}
        
        # Prepare prompts for LLM
        prompts_data = [
            {"id": prompt["id"], "question": prompt["question"], "page_name": page_name}
            for prompt, page_name in prompts_with_pages
        ]
        
        system_prompt = """Du klassifizierst deutschsprachige Fragen aus einem Gesprächsprotokoll für Recruiting-Gespräche.

Gib NUR valides JSON zurück. Keine zusätzlichen Erklärungen.

═══════════════════════════════════════════════════════════════════
VERFÜGBARE LABELS (mit Erklärung)
═══════════════════════════════════════════════════════════════════

- yes_no: Binäre Ja/Nein-Frage ohne Details
- yes_no_with_details: Ja/Nein-Frage mit zusätzlichen Details (z.B. "seit wann?")
- text: Freie Texteingabe (Beschreibung, Erklärung)
- text_list: Liste von Texten (mehrere Items)
- number: Numerischer Wert (Anzahl, Menge)
- date: Datum oder Zeitpunkt
- routing_rule: Routing-Entscheidung im Gesprächsfluss
- info: Nur zur Anzeige, keine Eingabe erforderlich
- recruiter_instruction: Anweisung für den Recruiter (enthält oft "!!!")

═══════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLES (Lerne aus diesen Beispielen)
═══════════════════════════════════════════════════════════════════

BEISPIEL 1:
Frage: "Zwingend: Führerschein Klasse B vorhanden?"
→ {
  "prompt_id": 1,
  "inferred_type": "yes_no",
  "confidence": 0.98,
  "reasoning": "Binäre Anforderung mit Zwingend-Präfix"
}

BEISPIEL 2:
Frage: "Welche Fortbildungen haben Sie in den letzten Jahren absolviert?"
→ {
  "prompt_id": 2,
  "inferred_type": "text_list",
  "confidence": 0.95,
  "reasoning": "Fragt nach mehreren Items (Fortbildungen)"
}

BEISPIEL 3:
Frage: "Wünschenswert: Erfahrung in Projektleitung (seit wann?)"
→ {
  "prompt_id": 3,
  "inferred_type": "yes_no_with_details",
  "confidence": 0.92,
  "reasoning": "Ja/Nein-Frage mit zusätzlicher Zeitangabe"
}

BEISPIEL 4:
Frage: "Seit wann sind Sie in Ihrer aktuellen Position tätig?"
→ {
  "prompt_id": 4,
  "inferred_type": "date",
  "confidence": 0.94,
  "reasoning": "Fragt nach einem konkreten Zeitpunkt"
}

BEISPIEL 5:
Frage: "Akzeptieren Sie Vollzeit (40 Stunden/Woche)?"
→ {
  "prompt_id": 5,
  "inferred_type": "yes_no",
  "confidence": 0.96,
  "reasoning": "Binäre Akzeptanzfrage für Arbeitszeit"
}

BEISPIEL 6:
Frage: "Station: Intensivstation, Geriatrie, Kardiologie, ZNA"
→ {
  "prompt_id": 6,
  "inferred_type": "text",
  "confidence": 0.94,
  "reasoning": "Auswahlfrage mit mehreren Optionen (Kandidat wählt eine oder mehrere)"
}

BEISPIEL 7:
Frage: "Vollzeit: 38,5Std/Woche"
→ {
  "prompt_id": 7,
  "inferred_type": "yes_no_with_details",
  "confidence": 0.92,
  "reasoning": "Arbeitszeitfrage mit konkreter Stundenzahl"
}

BEISPIEL 8:
Frage: "Teilzeit: flexibel"
→ {
  "prompt_id": 8,
  "inferred_type": "yes_no_with_details",
  "confidence": 0.91,
  "reasoning": "Arbeitszeitfrage mit Flexibilitätsangabe"
}
  "prompt_id": 5,
  "inferred_type": "yes_no",
  "confidence": 0.98,
  "reasoning": "Ja/Nein-Frage zu Rahmenbedingung"
}

BEISPIEL 6:
Frage: "Beschreiben Sie Ihre wichtigsten Aufgaben in der letzten Position."
→ {
  "prompt_id": 6,
  "inferred_type": "text",
  "confidence": 0.96,
  "reasoning": "Fordert freie Beschreibung"
}

BEISPIEL 7:
Frage: "Bitte unbedingt erwähnen: Attraktives Gehalt und Bonussystem!!!"
→ {
  "prompt_id": 7,
  "inferred_type": "recruiter_instruction",
  "confidence": 1.0,
  "reasoning": "Instruktion für Recruiter (enthält '!!!')"
}

BEISPIEL 8:
Frage: "Wie viele Jahre Berufserfahrung haben Sie im Bereich IT?"
→ {
  "prompt_id": 8,
  "inferred_type": "number",
  "confidence": 0.93,
  "reasoning": "Fragt nach numerischem Wert (Jahre)"
}

BEISPIEL 9:
Frage: "Information: Die Position ist unbefristet und startet ab sofort."
→ {
  "prompt_id": 9,
  "inferred_type": "info",
  "confidence": 0.99,
  "reasoning": "Reine Information, keine Frage"
}

BEISPIEL 10:
Frage: "Hat der Kandidat Interesse? Falls nein, Gespräch beenden."
→ {
  "prompt_id": 10,
  "inferred_type": "routing_rule",
  "confidence": 0.91,
  "reasoning": "Enthält Routing-Logik (Falls...dann)"
}

═══════════════════════════════════════════════════════════════════
KLASSIFIZIERUNGS-HINWEISE
═══════════════════════════════════════════════════════════════════

1. KONTEXT beachten:
   - page_name kann Hinweise geben (z.B. "Info-Seite" → wahrscheinlich "info")
   - "Zwingend:"/"Wünschenswert:" → meistens "yes_no"

2. FORMULIERUNG analysieren:
   - "Welche...?" + Plural → oft "text_list"
   - "Seit wann...?" → oft "date" oder "yes_no_with_details"
   - "Wie viele...?" → oft "number"
   - Enthält "!!!" → wahrscheinlich "recruiter_instruction"

3. CONFIDENCE-Werte:
   - 0.95-1.0: Sehr sicher (klare Signalwörter)
   - 0.85-0.94: Sicher (typische Formulierung)
   - 0.70-0.84: Moderat (einige Indikatoren)
   - <0.70: Unsicher (Fallback auf "text")

═══════════════════════════════════════════════════════════════════
OUTPUT-FORMAT
═══════════════════════════════════════════════════════════════════

Für jede Frage gib zurück:
{
  "prompts": [
    {
      "prompt_id": <int>,
      "inferred_type": "<label>",
      "confidence": <0.0-1.0>,
      "reasoning": "Kurze, präzise Begründung"
    }
  ]
}

WICHTIG:
- Analysiere JEDE Frage einzeln
- Nutze die Examples als Orientierung
- Im Zweifel: "text" als Fallback (confidence < 0.7)

═══════════════════════════════════════════════════════════════════
ERWEITERTE ERKENNUNGSREGELN (KRITISCH!)
═══════════════════════════════════════════════════════════════════

1. QUALIFIKATIONSFRAGEN erkennen:
   Keywords: "Ausbildung", "Studium", "Zertifikat", "Erfahrung", "Jahre"
   → Meist: "yes_no" (wenn "Haben Sie...?")
   → Manchmal: "text" (wenn "Welche Ausbildung...?")

2. AUSWAHLFRAGEN MIT MEHREREN OPTIONEN:
   Format: "Station: Intensivstation, Notaufnahme, Innere Medizin"
   → type: "text" (nicht "yes_no"!)
   → Kandidat wählt eine oder mehrere aus

3. ARBEITSZEITFRAGEN MIT STUNDENZAHL:
   Format: "Vollzeit: 38,5 Std/Woche" oder "Teilzeit: flexibel"
   → type: "yes_no_with_details"
   → Es gibt meist BEIDE Fragen (Vollzeit UND Teilzeit)

4. JA/NEIN MIT NACHFRAGE:
   "Haben Sie X?" + "Falls ja, welche?"
   → Erste Frage: "yes_no"
   → Zweite Frage: "text" oder "text_list"

5. MEHRZEILIGE BESCHREIBUNGEN:
   "Beschreiben Sie Ihre Aufgaben", "Was motiviert Sie?"
   → type: "text" (nicht "text_list"!)
   → Lange Antworten erwartet

✅ Bei Unsicherheit zwischen "yes_no" und "text":
   → Schaue auf konkrete Formulierung
   → "Haben Sie...?" → yes_no
   → "Welche... haben Sie?" → text/text_list

✅ Bei Unsicherheit zwischen "text" und "text_list":
   → Einzelne Sache erwartet → text
   → Mehrere Dinge/Aufzählung → text_list
"""
        
        user_prompt = f"""Klassifiziere diese Prompts nach dem Schema der Examples:

{json.dumps(prompts_data, indent=2, ensure_ascii=False)}

Antworte nur mit JSON im angegebenen Format."""
        
        try:
            # Use LLM client (defaults to GPT-4o for TypeEnricher, works well)
            response_text = self.llm_client.create_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=2000
            )
            
            # Parse response
            classifications = json.loads(response_text)
            
            # Handle both array and object responses
            if isinstance(classifications, dict) and "prompts" in classifications:
                classifications = classifications["prompts"]
            elif isinstance(classifications, dict):
                classifications = [classifications]
            
            for item in classifications:
                results[item["prompt_id"]] = ShadowType(
                    prompt_id=item["prompt_id"],
                    inferred_type=PromptType(item["inferred_type"]),
                    confidence=item.get("confidence", 0.8),
                    reasoning=item.get("reasoning", "LLM classification")
                )
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ [TYPE_ENRICHER] LLM classification failed, using fallback: {e}")
            print(f"Warning: LLM classification failed: {e}")
            # Fallback to safe defaults
            for prompt, page_name in prompts_with_pages:
                results[prompt["id"]] = ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=PromptType.TEXT,
                    confidence=0.5,
                    reasoning=f"Fallback due to error: {e}"
                )
        
        return results


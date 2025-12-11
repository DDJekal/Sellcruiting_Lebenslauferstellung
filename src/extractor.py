"""Extractor for filling prompts from transcript using LLM."""
import os
import json
from typing import Dict, Any, List
from openai import OpenAI

from models import ShadowType, PromptAnswer, Evidence, PromptType


class Extractor:
    """Extracts prompt answers from transcript using LLM."""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key."""
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    
    def extract(
        self,
        transcript: List[Dict[str, str]],
        shadow_types: Dict[int, ShadowType],
        grounding: Dict[str, Any],
        prompts_to_fill: List[Dict[str, Any]]
    ) -> Dict[int, PromptAnswer]:
        """Extract answers for prompts from transcript."""
        
        # Filter out info prompts (they don't need filling)
        fillable_prompts = [
            p for p in prompts_to_fill
            if p["id"] in shadow_types and shadow_types[p["id"]].inferred_type not in [PromptType.INFO, PromptType.RECRUITER_INSTRUCTION]
        ]
        
        if not fillable_prompts:
            return {}
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            transcript, shadow_types, grounding, fillable_prompts
        )
        
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
            
            # Parse into PromptAnswer objects
            answers = {}
            prompts_data = result.get("prompts", [])
            
            for item in prompts_data:
                prompt_id = item["prompt_id"]
                
                # Parse evidence
                evidence_list = []
                for ev in item.get("evidence", []):
                    evidence_list.append(Evidence(
                        span=ev.get("span", ""),
                        turn_index=ev.get("turn_index", 0),
                        speaker=ev.get("speaker")
                    ))
                
                answers[prompt_id] = PromptAnswer(
                    checked=item.get("checked"),
                    value=item.get("value"),
                    confidence=item.get("confidence", 0.8),
                    evidence=evidence_list,
                    notes=item.get("notes")
                )
            
            return answers
        
        except Exception as e:
            print(f"Error in extraction: {e}")
            # Return empty answers with error notes
            return {
                p["id"]: PromptAnswer(
                    checked=None,
                    value=None,
                    confidence=0.0,
                    evidence=[],
                    notes=f"Extraction error: {str(e)}"
                )
                for p in fillable_prompts
            }
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with extraction rules."""
        return """Du bist ein Experte für das Ausfüllen von Gesprächsprotokollen aus Telefon-Transkripten.

AUFGABE:
- Fülle die Prompts aus dem Transkript
- Antworte NUR als valides JSON (kein zusätzlicher Text)
- Für JEDE Antwort: evidence[{span, turn_index, speaker}] angeben
- Keine Halluzinationen: lieber null + notes

REGELN FÜR yes_no-PROMPTS:
- checked: true, value: "ja" → Kandidat stimmt zu:
  1. EXPLIZIT: "ja", "passt", "würde gehen", "ist okay", "in ordnung", "genau", "richtig"
  2. IMPLIZIT (nur bei Rahmenbedingungen/Angeboten): Recruiter erwähnt Angebot/Bedingung UND:
     - Kandidat widerspricht NICHT
     - Gespräch geht normal weiter (kein Abbruch, keine Bedenken)
     - confidence: 0.8, notes: "Implizit akzeptiert (kein Widerspruch)"
     - WICHTIG: Evidence muss die Erwähnung durch Recruiter enthalten
- checked: false, value: "nein" → Kandidat lehnt ab:
  - EXPLIZIT: "nein", "geht nicht", "kommt nicht in frage", "das passt mir nicht"
  - IMPLIZIT: Kandidat äußert Bedenken, Zweifel, oder stellt Bedingungen
- checked: null, value: null → Nicht im Gespräch erwähnt (confidence: 0.0, notes: "nicht erwähnt")

REGELN FÜR text_list-PROMPTS (z.B. Fortbildungen):
- Durchsuche GESAMTES Transkript nach allen Nennungen
- Erstelle vollständige Liste aller Items
- Jedes Item mit separatem evidence-Eintrag
- Format: ["Item1 (Jahr)", "Item2 (Jahr)", ...]

REGELN FÜR yes_no_with_details:
- checked: wie bei yes_no
- value: zusätzliche Details (z.B. "2 Jahre", "seit 2019")

EVIDENZ-SNIPPETS:
- Kurz halten (Keyword ± 30 Zeichen Kontext)
- turn_index angeben (0-basiert)
- speaker angeben ("A" = Kandidat, "B" = Recruiter)

OUTPUT-SCHEMA:
{
  "prompts": [
    {
      "prompt_id": <int>,
      "checked": true|false|null,
      "value": null|string|array,
      "confidence": <0.0-1.0>,
      "evidence": [
        {"span": "...", "turn_index": <int>, "speaker": "A"|"B"}
      ],
      "notes": "..."
    }
  ]
}"""
    
    def _build_user_prompt(
        self,
        transcript: List[Dict[str, str]],
        shadow_types: Dict[int, ShadowType],
        grounding: Dict[str, Any],
        prompts: List[Dict[str, Any]]
    ) -> str:
        """Build user prompt with context."""
        n_turns = len(transcript)
        
        # AIDA phase hints (simple turn ranges)
        interest_range = (0, int(n_turns * 0.6))
        action_range = (int(n_turns * 0.5), n_turns)
        
        # Prepare prompts with types
        prompts_with_types = []
        for p in prompts:
            shadow = shadow_types[p["id"]]
            prompts_with_types.append({
                "prompt_id": p["id"],
                "question": p["question"],
                "inferred_type": shadow.inferred_type.value
            })
        
        prompt_text = f"""MANDANTEN-GROUNDING:
{json.dumps(grounding, indent=2, ensure_ascii=False)}

AIDA-STRUKTUR (Orientierung für Suche):
- Qualifikationen/Kriterien: meist in Turns {interest_range[0]}-{interest_range[1]}
- Rahmenbedingungen: meist in Turns {action_range[0]}-{action_range[1]}

TRANSKRIPT ({len(transcript)} Turns):
"""
        
        # Add transcript with turn indices
        for i, turn in enumerate(transcript):
            prompt_text += f"\n[Turn {i}] {turn['speaker']}: {turn['text']}"
        
        prompt_text += f"\n\nZU FÜLLENDE PROMPTS:\n{json.dumps(prompts_with_types, indent=2, ensure_ascii=False)}"
        
        # Add hint about implicit acceptance
        prompt_text += """

WICHTIGER HINWEIS ZUR IMPLIZITEN ZUSTIMMUNG:
Bei Rahmenbedingungen (Gehalt, Vollzeit, Arbeitsvertrag, Urlaub, etc.):
- Wenn der Recruiter das Angebot erwähnt (auch in längeren Absätzen!) UND der Kandidat das Gespräch normal fortsetzt
- OHNE Bedenken zu äußern oder Bedingungen zu stellen
- DANN gilt das als implizite Zustimmung (checked: true, confidence: 0.8)
- Evidence muss die relevante Recruiter-Aussage enthalten (auch aus langen Texten!)

WICHTIG: Durchsuche lange Recruiter-Monologe sorgfältig nach Angeboten/Rahmenbedingungen!

Beispiele:
1. Recruiter: "Unbefristeter Arbeitsvertrag wäre das dann."
   Kandidat: [sagt nichts dagegen, Gespräch geht weiter]
   → checked: true, value: "ja", confidence: 0.8, notes: "Implizit akzeptiert"

2. Recruiter: "...attraktives Grundgehalt plus leistungsabhängige Erfolgsbeteiligung..."
   Kandidat: [keine Ablehnung, Gespräch geht weiter]
   → checked: true, value: "ja", confidence: 0.8, notes: "Implizit akzeptiert"

FÜLLE NUN DAS PROTOKOLL (als JSON):"""
        
        return prompt_text


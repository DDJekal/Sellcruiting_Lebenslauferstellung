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

═══════════════════════════════════════════════════════════════════
REGELN FÜR QUALIFIKATIONSFRAGEN (HÖCHSTE PRIORITÄT)
═══════════════════════════════════════════════════════════════════

Qualifikationsfragen erkennen an Keywords:
- Ausbildung/Studium: "Haben Sie eine Ausbildung...", "Haben Sie studiert..."
- Berufserfahrung: "Haben Sie Erfahrung...", "Wie lange arbeiten Sie..."
- Zertifikate: "Besitzen Sie...", "Haben Sie den Nachweis..."
- Sprachkenntnisse: "Sprechen Sie...", "Deutschkenntnisse..."
- Führerschein: "Haben Sie einen Führerschein..."

⚠️ WICHTIG: Qualifikationen erfordern FAKTISCHE ANTWORTEN (nicht nur Zustimmung)

✅ checked: true → Kandidat HAT die Qualifikation:

  1. DIREKTE BESTÄTIGUNG (confidence: 0.95-1.0):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Ja, ich habe eine Ausbildung als Pflege-      │
  │            fachmann abgeschlossen."                       │
  │ → checked: true, value: "ja", confidence: 0.95           │
  └──────────────────────────────────────────────────────────┘
  
  2. IMPLIZITE BESTÄTIGUNG durch Details (confidence: 0.85-0.93):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie Berufserfahrung in der Pflege?"        │
  │ Kandidat: "Ich arbeite seit 2020 bei den HEH-Kliniken    │
  │            als Pflegefachmann."                           │
  │ → checked: true, value: "seit 2020", confidence: 0.92    │
  │ → notes: "Implizit durch Positionsnennung bestätigt"     │
  └──────────────────────────────────────────────────────────┘
  
  3. BEILÄUFIGE ERWÄHNUNG im Lebenslauf-Teil (confidence: 0.80-0.90):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat (früher im Gespräch): "...dann habe ich 2020    │
  │           meine Ausbildung zum Pflegefachmann fertig      │
  │           gemacht..."                                     │
  │ → checked: true, value: "ja (2020)", confidence: 0.88    │
  │ → notes: "Beiläufig im Lebenslauf erwähnt"               │
  └──────────────────────────────────────────────────────────┘
  
  4. ÄQUIVALENTE QUALIFIKATION (confidence: 0.85-0.92):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Ich bin ausgebildeter Gesundheits- und        │
  │            Krankenpfleger."                               │
  │ → checked: true, value: "Gesundheits- und Kranken-       │
  │                          pfleger", confidence: 0.90       │
  │ → notes: "Äquivalente Qualifikation im Pflegebereich"    │
  └──────────────────────────────────────────────────────────┘

❌ checked: false → Kandidat HAT die Qualifikation NICHT:
  - Explizite Verneinung: "Nein, habe ich nicht"
  - Andere Qualifikation: "Ich bin Restaurantfachmann" (bei Frage nach Koch)

⚠️ checked: null → UNKLAR oder NICHT ERWÄHNT:
  - Qualifikation wird nirgendwo im Transkript erwähnt
  - Unklare Antwort ohne konkrete Qualifikation

KRITISCH für Qualifikationen:
✅ Durchsuche das GESAMTE Transkript - oft werden Qualifikationen zu Beginn erwähnt
✅ Auch Lebenslauf-Abschnitte beachten: "dann habe ich die Ausbildung bei..."
✅ Bei Mehrfachoptionen ("A oder B oder C?"): Wenn EINE Option erfüllt → checked: true
✅ Äquivalente Qualifikationen akzeptieren (z.B. "Krankenpfleger" für "Pflegefachmann")

═══════════════════════════════════════════════════════════════════
REGELN FÜR yes_no-PROMPTS (Rahmenbedingungen)
═══════════════════════════════════════════════════════════════════

✅ checked: true, value: "ja" → Kandidat stimmt EINDEUTIG zu:
  
  1. EXPLIZITE ZUSTIMMUNG (confidence: 0.95-1.0):
     - "ja", "genau", "passt", "absolut", "auf jeden Fall"
     - "würde gehen", "ist okay", "in Ordnung", "kein Problem"
     - "das passt mir", "damit kann ich leben"
  
  2. IMPLIZITE ZUSTIMMUNG (confidence: 0.80-0.90):
     Nur wenn ALLE Bedingungen erfüllt:
     a) Recruiter erwähnt Rahmenbedingung/Angebot klar und deutlich
     b) UND Kandidat reagiert POSITIV:
        - Stellt Folgefrage zum Thema (zeigt Interesse)
        - Sagt "gut", "schön", "prima" (auch wenn kurz)
        - Antwortet mit relevantem Detail
     c) UND Gespräch geht konstruktiv weiter (kein Abbruch)
     
     BEISPIEL AKZEPTIERT:
     ┌─────────────────────────────────────────────────┐
     │ Recruiter: "30 Tage Urlaub plus Sonderurlaub."  │
     │ Kandidat: "Und wie sieht es mit Homeoffice aus?"│
     │ → checked: true, confidence: 0.85               │
     │ → notes: "Implizit - Folgefrage zeigt Akzeptanz"│
     └─────────────────────────────────────────────────┘

❌ checked: false, value: "nein" → Kandidat lehnt EINDEUTIG ab:
  
  1. EXPLIZITE ABLEHNUNG (confidence: 0.95-1.0):
     - "nein", "geht nicht", "passt nicht", "kommt nicht in Frage"
     - "das ist zu wenig", "das reicht mir nicht"
     - "da kann ich nicht", "damit habe ich ein Problem"
  
  2. IMPLIZITE ABLEHNUNG (confidence: 0.80-0.90):
     - Kandidat äußert Bedenken: "hmm, schwierig", "weiß nicht"
     - Kandidat stellt Bedingungen: "nur wenn...", "müsste..."
     - Kandidat weicht aus: "mal sehen", "muss überlegen"

⚠️ checked: null, value: null → NICHT KLAR (confidence: 0.0):
  
  Diese Situationen sind KEINE Zustimmung:
  1. Kandidat sagt GAR NICHTS zur Bedingung
  2. Kandidat antwortet nur "hmm", "okay" (unspezifisch, kein Bezug)
  3. Kandidat wechselt SOFORT das Thema (ignoriert Aussage)
  4. Lange Pause (>3 Turns) zwischen Erwähnung und Reaktion
  5. Recruiter erwähnt Bedingung, aber Gespräch wird unterbrochen
  6. Telefonstörung während relevanter Passage
  7. Ambivalente Antwort: "mal sehen", "vielleicht"
  
  BEISPIEL NICHT AKZEPTIERT:
  ┌─────────────────────────────────────────────────┐
  │ Recruiter: "30 Tage Urlaub plus Sonderurlaub."  │
  │ Kandidat: "Hmm."                                 │
  │ Recruiter: "Haben Sie noch andere Fragen?"      │
  │ → checked: null, confidence: 0.0                │
  │ → notes: "Keine klare Reaktion, Thema gewechselt"│
  └─────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════
REGELN FÜR text_list-PROMPTS (z.B. Fortbildungen)
═══════════════════════════════════════════════════════════════════

- Durchsuche GESAMTES Transkript nach ALLEN Nennungen
- Erstelle vollständige Liste aller Items
- Jedes Item mit separatem evidence-Eintrag
- Format: ["Item1 (Jahr)", "Item2 (Jahr)", ...]
- NICHT: Ein Item vergessen, weil es spät im Gespräch kam

═══════════════════════════════════════════════════════════════════
REGELN FÜR yes_no_with_details
═══════════════════════════════════════════════════════════════════

- checked: wie bei yes_no (siehe oben)
- value: zusätzliche Details (z.B. "2 Jahre", "seit 2019", "40 Stunden/Woche")
- Evidence muss BEIDE Aspekte abdecken (Zustimmung + Detail)

═══════════════════════════════════════════════════════════════════
EVIDENZ-SNIPPETS (QUALITÄTSANFORDERUNGEN)
═══════════════════════════════════════════════════════════════════

1. SPAN-LÄNGE:
   - Minimum: Keyword + 20 Zeichen Kontext
   - Maximum: 100 Zeichen
   - Muss die Aussage VOLLSTÄNDIG enthalten

2. PRÄZISION:
   - Bei yes_no: Muss Zustimmung/Ablehnung klar zeigen
   - Bei text_list: Jedes Item = separater Evidence-Eintrag
   - Bei yes_no_with_details: Evidence muss Details enthalten

3. TURN_INDEX:
   - Immer angeben (0-basiert)
   - Bei impliziter Zustimmung: BEIDE Turns angeben:
     * Recruiter-Aussage (Turn X)
     * Kandidat-Reaktion (Turn X+1 oder X+2)

4. BEISPIEL GUTE EVIDENCE (implizite Zustimmung):
{
  "checked": true,
  "value": "ja",
  "confidence": 0.85,
  "evidence": [
    {
      "span": "30 Tage Urlaub plus Sonderurlaub",
      "turn_index": 45,
      "speaker": "B"
    },
    {
      "span": "Und wie sieht es mit Homeoffice aus",
      "turn_index": 46,
      "speaker": "A"
    }
  ],
  "notes": "Implizit akzeptiert - Kandidat stellt interessierte Folgefrage"
}

5. BEISPIEL SCHLECHTE EVIDENCE (zu vage):
{
  "checked": true,
  "value": "ja",
  "confidence": 0.85,
  "evidence": [
    {
      "span": "okay",  ❌ ZU KURZ
      "turn_index": 46,
      "speaker": "A"
    }
  ],
  "notes": "Implizit"  ❌ ZU VAGE
}

═══════════════════════════════════════════════════════════════════
OUTPUT-SCHEMA
═══════════════════════════════════════════════════════════════════

{
  "prompts": [
    {
      "prompt_id": <int>,
      "checked": true|false|null,
      "value": null|string|array,
      "confidence": <0.0-1.0>,
      "evidence": [
        {
          "span": "...",
          "turn_index": <int>,
          "speaker": "A"|"B"
        }
      ],
      "notes": "Detaillierte Begründung für die Entscheidung"
    }
  ]
}

KRITISCHE HINWEISE:
❌ Im Zweifel: checked = null (lieber vorsichtig als False Positive)
✅ Explizite Aussagen haben Vorrang vor impliziten
✅ "Hmm", "okay" alleine ist KEINE Zustimmung
✅ Notes müssen erklären, warum confidence < 0.95
"""
    
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

═══════════════════════════════════════════════════════════════════
WICHTIGE HINWEISE ZUR IMPLIZITEN ZUSTIMMUNG
═══════════════════════════════════════════════════════════════════

Bei Rahmenbedingungen (Gehalt, Vollzeit, Arbeitsvertrag, Urlaub, etc.):

✅ AKZEPTIERT als implizite Zustimmung (confidence: 0.80-0.90):
   Wenn ALLE Kriterien erfüllt:
   1. Recruiter erwähnt das Angebot/Bedingung explizit (auch in langen Absätzen!)
   2. Kandidat reagiert POSITIV (Folgefrage, "gut", "schön", relevantes Detail)
   3. Gespräch geht konstruktiv weiter
   
   Evidence muss BEIDE Turns enthalten (Recruiter + Kandidat)

❌ NICHT akzeptiert (checked: null):
   1. Kandidat sagt gar nichts zur Bedingung
   2. Nur "hmm" oder "okay" ohne Bezug zum Thema
   3. Kandidat wechselt sofort das Thema
   4. Lange Pause (>3 Turns) zwischen Erwähnung und Reaktion
   5. Ambivalente Antworten: "mal sehen", "vielleicht", "muss ich überlegen"

BEISPIEL 1 - ✅ IMPLIZITE ZUSTIMMUNG:
┌───────────────────────────────────────────────────────────────┐
│ [Turn 45] B: "Unbefristeter Vertrag mit 30 Tagen Urlaub."     │
│ [Turn 46] A: "Das klingt gut. Gibt es Homeoffice?"            │
│                                                                │
│ → checked: true, value: "ja", confidence: 0.85                │
│ → evidence: [                                                  │
│     {span: "Unbefristeter Vertrag mit 30 Tagen Urlaub",       │
│      turn_index: 45, speaker: "B"},                           │
│     {span: "Das klingt gut. Gibt es Homeoffice",              │
│      turn_index: 46, speaker: "A"}                            │
│   ]                                                            │
│ → notes: "Implizit akzeptiert - positive Reaktion + Folgefrage"│
└───────────────────────────────────────────────────────────────┘

BEISPIEL 2 - ❌ KEINE ZUSTIMMUNG:
┌───────────────────────────────────────────────────────────────┐
│ [Turn 45] B: "Unbefristeter Vertrag mit 30 Tagen Urlaub."     │
│ [Turn 46] A: "Hmm."                                            │
│ [Turn 47] B: "Haben Sie noch Fragen zur Position?"            │
│                                                                │
│ → checked: null, value: null, confidence: 0.0                 │
│ → evidence: []                                                 │
│ → notes: "Keine klare Reaktion - Recruiter wechselt Thema"    │
└───────────────────────────────────────────────────────────────┘

WICHTIG: 
- Durchsuche lange Recruiter-Monologe sorgfältig nach Angeboten!
- Im Zweifel: checked = null (lieber vorsichtig)
- "Hmm"/"okay" alleine ist KEINE Zustimmung

FÜLLE NUN DAS PROTOKOLL (als JSON):"""
        
        return prompt_text


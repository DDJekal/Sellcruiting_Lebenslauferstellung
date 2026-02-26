"""Extractor for filling prompts from transcript using LLM."""
import os
import json
from typing import Dict, Any, List

from models import ShadowType, PromptAnswer, Evidence, PromptType
from llm_client import LLMClient


class Extractor:
    """Extracts prompt answers from transcript using LLM."""
    
    def __init__(self, api_key: str = None, prefer_claude: bool = True):
        """
        Initialize with LLM client.
        
        Args:
            api_key: Deprecated (uses env vars now)
            prefer_claude: Use Claude Sonnet 4.5 primary, GPT-4o fallback
        """
        self.llm_client = LLMClient(prefer_claude=prefer_claude)
    
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
            # Use Claude with OpenAI fallback
            response_text = self.llm_client.create_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=4000
            )
            
            result = json.loads(response_text)
            
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
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ [EXTRACTOR] JSON parsing error, using fallback: {e}")
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

⚠️ GRUNDPRINZIP: STRIKTE AUSWERTUNG - Nur explizite Bestätigungen zählen!
⚠️ WICHTIG: Berufserfahrung ist NICHT gleich formale Ausbildung!

Qualifikationsfragen erkennen an Keywords:
- Ausbildung/Studium: "Haben Sie eine Ausbildung...", "Haben Sie studiert..."
- Berufserfahrung: "Haben Sie Erfahrung...", "Wie lange arbeiten Sie..."
- Zertifikate: "Besitzen Sie...", "Haben Sie den Nachweis..."
- Sprachkenntnisse: "Sprechen Sie...", "Deutschkenntnisse...", "Deutsch B2", "B2", "C1"
- Führerschein: "Haben Sie einen Führerschein..."

⚠️ WICHTIG: Auch Fragen mit nur "Deutsch B2" (OHNE "kenntnisse") sind SPRACHFRAGEN!
Beispiel: "zwingend: Deutsch B2" → ist eine Sprachkenntnisse-Frage!

═══════════════════════════════════════════════════════════════════

✅ checked: true → NUR bei EXPLIZITER Bestätigung:

  1. DIREKTE BESTÄTIGUNG (confidence: 0.95-1.0):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Ja, ich habe eine Ausbildung als Pflege-      │
  │            fachmann abgeschlossen."                       │
  │ → checked: true, value: "ja", confidence: 0.95           │
  └──────────────────────────────────────────────────────────┘
  
  2. BESTÄTIGUNG MIT DETAILS (confidence: 0.95-1.0):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Ja, 2020 abgeschlossen in Nürnberg."          │
  │ → checked: true, value: "ja (2020, Nürnberg)"           │
  │ → confidence: 0.98                                        │
  └──────────────────────────────────────────────────────────┘

❌ checked: false → Bei Verneinung oder anderer Qualifikation:

  1. EXPLIZITE VERNEINUNG (confidence: 0.95-1.0):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Nein, das habe ich nicht."                    │
  │                                                           │
  │ → checked: false ❌                                       │
  │ → value: "nein"                                          │
  │ → confidence: 0.95                                        │
  │ → notes: "Explizite Verneinung"                          │
  └──────────────────────────────────────────────────────────┘
  
  2. BERUFSERFAHRUNG OHNE FORMALE AUSBILDUNG (confidence: 0.85-0.90):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Nein, aber ich arbeite seit 7 Jahren in der   │
  │            Pflege."                                       │
  │                                                           │
  │ → checked: false ❌                                       │
  │ → value: "nein (7 Jahre Berufserfahrung, keine formale   │
  │            Ausbildung)"                                   │
  │ → confidence: 0.90                                        │
  │ → notes: "Berufserfahrung vorhanden, aber keine formale  │
  │          Ausbildung"                                      │
  └──────────────────────────────────────────────────────────┘
  
  3. ANDERE QUALIFIKATION (confidence: 0.85-0.92):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Nein, ich bin Altenpfleger."                  │
  │                                                           │
  │ → checked: false ❌                                       │
  │ → value: "nein (Altenpfleger)"                           │
  │ → confidence: 0.90                                        │
  │ → notes: "Andere Qualifikation: Altenpfleger"            │
  └──────────────────────────────────────────────────────────┘
  
  4. KOMPLETT ANDERE BRANCHE (confidence: 0.95-1.0):
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"   │
  │ Kandidat: "Nein, ich bin IT-Spezialist."                 │
  │                                                           │
  │ → checked: false ❌                                       │
  │ → value: "nein (IT-Spezialist)"                          │
  │ → confidence: 0.95                                        │
  │ → notes: "Komplett andere Branche"                       │
  └──────────────────────────────────────────────────────────┘

⚠️ checked: null → Wenn nicht klar angesprochen:

  BEISPIEL: THEMA NICHT ERWÄHNT
  ┌──────────────────────────────────────────────────────────┐
  │ Frage: "Haben Sie Fortbildungen besucht?"                │
  │ Transkript: [Thema Fortbildungen wird nicht erwähnt]     │
  │                                                           │
  │ → checked: null                                           │
  │ → value: null                                             │
  │ → confidence: 0.0                                         │
  │ → notes: "Nicht im Gespräch angesprochen"                │
  └──────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════
⚠️ AUSLÄNDISCHE ABSCHLÜSSE - DEUTSCHE ANERKENNUNG (KRITISCH!)
═══════════════════════════════════════════════════════════════════

⚠️ SPEZIALFALL: Ausländische Ausbildung/Studium

🚨 KRITISCH: DURCHSUCHE DAS GESAMTE TRANSKRIPT NACH ANERKENNUNG!

Bei ausländischer Ausbildung/Studium:
1. Suche ALLE Turns nach Anerkennung-Keywords:
   - "anerkannt", "Anerkennung", "Gleichwertigkeit", "gleichwertig"
   - "Regierungspräsidium", "IHK", "Kultusministerium", "ZAB"
   - "Gleichwertigkeitsbescheinigung", "Anerkennungsbescheid"
   - Auch Kurzformen: "anerkannte", "anerkannt in Deutschland"
   
2. Erstelle MEHRERE Evidence-Einträge:
   - Evidence 1: "in [Land] gemacht" (Turn X)
   - Evidence 2: "anerkannt in Deutschland" (Turn Y) ODER
   - Evidence 2: FEHLT → checked: false

3. Wenn Anerkennung NUR erwähnt als:
   - "beantragt", "läuft noch", "wird noch geprüft", "habe ich noch nicht"
   → checked: false
   → notes: "Anerkennung beantragt aber noch nicht erhalten"

4. Wenn GAR KEINE Erwähnung von Anerkennung bei ausländischem Abschluss:
   → checked: false
   → notes: "Ausländische Ausbildung ohne Nachweis deutscher Anerkennung"

5. Reglementierte Berufe (Pflege, Medizin, Lehramt, Erziehung):
   → Anerkennung ist PFLICHT
   → Ohne Anerkennung IMMER checked: false

PRÜFE IMMER ob deutsche Anerkennung erwähnt wird!

✅ AUSLÄNDISCH MIT deutscher Anerkennung → checked: true:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"        │
│ Kandidat: "Ja, in der Türkei gemacht und 2023 vom             │
│            Regierungspräsidium in Deutschland anerkannt."      │
│                                                                 │
│ → checked: true ✅                                              │
│ → value: "Pflegefachmann (Türkei, in Deutschland anerkannt)"  │
│ → confidence: 0.95                                              │
│ → notes: "Ausländische Ausbildung mit deutscher Anerkennung   │
│          (Regierungspräsidium, 2023)"                          │
│ → evidence: [                                                   │
│     {span: "in der Türkei gemacht", turn_index: X, ...},       │
│     {span: "anerkannt", turn_index: Y, ...}                    │
│   ] (MEHRERE Evidence-Einträge!)                               │
└────────────────────────────────────────────────────────────────┘

❌ AUSLÄNDISCH OHNE deutsche Anerkennung → checked: false:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"        │
│ Kandidat: "Ja, in der Türkei habe ich das gelernt."           │
│                                                                 │
│ → checked: false ❌                                             │
│ → value: "Pflegefachmann (Türkei, keine deutsche Anerkennung)"│
│ → confidence: 0.90                                              │
│ → notes: "Ausländische Ausbildung ohne deutsche Anerkennung - │
│          nicht qualifiziert für reglementierte Berufe"         │
└────────────────────────────────────────────────────────────────┘

⚠️ AUSLÄNDISCH + Anerkennung BEANTRAGT → checked: false:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"        │
│ Kandidat: "Ja, aus Syrien. Die Anerkennung habe ich           │
│            beantragt, läuft noch."                             │
│                                                                 │
│ → checked: false ❌                                             │
│ → value: "Pflegefachmann (Syrien, Anerkennung beantragt)"    │
│ → confidence: 0.85                                              │
│ → notes: "Ausländische Ausbildung, Anerkennung noch nicht     │
│          abgeschlossen - aktuell nicht qualifiziert"           │
└────────────────────────────────────────────────────────────────┘

✅ KEYWORDS FÜR ANERKENNUNG:
- "deutsche Anerkennung", "anerkannt in Deutschland"
- "Gleichwertigkeitsbescheinigung", "gleichwertig"
- "anerkannt vom [Behörde]", "Anerkennung durch [Behörde]"
- Behörden: Regierungspräsidium, IHK, Kultusministerium, ZAB

❌ KEYWORDS FÜR FEHLENDE ANERKENNUNG:
- "noch nicht anerkannt", "keine Anerkennung"
- "Anerkennung beantragt", "Anerkennungsverfahren läuft"
- "wird noch geprüft", "habe ich noch nicht"

⚠️ LÄNDER-ERKENNUNG (ausländische Ausbildung):
- Türkei, Syrien, Polen, Rumänien, Bulgarien, Ukraine, etc.
- "im Ausland", "nicht in Deutschland"
- Bei unklarem Land: Frage "Wo haben Sie gelernt?" beachten

✅ DEUTSCHE Ausbildung → checked: true (keine Anerkennung nötig!):
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"        │
│ Kandidat: "Ja, in Deutschland gemacht, in Nürnberg."          │
│                                                                 │
│ → checked: true ✅                                              │
│ → value: "Pflegefachmann (Deutschland)"                       │
│ → confidence: 0.95                                              │
│ → notes: "Deutsche Ausbildung"                                 │
└────────────────────────────────────────────────────────────────┘

⚠️ KRITISCHE REGEL:
Bei reglementierten Berufen (Pflege, Medizin, Lehramt, etc.) gilt:
→ Ausländischer Abschluss OHNE deutsche Anerkennung = checked: false
→ Nur MIT Anerkennung oder bei deutscher Ausbildung = checked: true

═══════════════════════════════════════════════════════════════════

❌ checked: false → NUR bei EINDEUTIGER NICHT-ERFÜLLUNG:
  - Explizite Verneinung: "Nein, das habe ich nicht"
  - Komplett andere Branche ohne Bezug: "Ich bin IT-Spezialist" (bei Frage nach Pflege)
  - Ausländische Ausbildung OHNE deutsche Anerkennung (siehe oben!)
  - Anerkennung beantragt aber noch nicht erhalten (siehe oben!)
  - ⚠️ NICHT bei unklaren Antworten oder fehlenden Details!

⚠️ checked: null → NUR wenn GAR NICHTS im Transkript:
  - Thema wird überhaupt nicht erwähnt
  - Keine relevanten Informationen vorhanden
  - ⚠️ NICHT verwenden wenn irgendwelche relevanten Infos da sind!

═══════════════════════════════════════════════════════════════════
MULTI-TURN REASONING FÜR QUALIFIKATIONEN (KRITISCH!)
═══════════════════════════════════════════════════════════════════

⚠️ WICHTIG: Qualifikationen werden oft ÜBER MEHRERE TURNS VERTEILT erwähnt!

✅ KOMBINIERE Informationen aus verschiedenen Turns:
┌────────────────────────────────────────────────────────────────┐
│ Turn 1: "Ich habe 2019 meine Ausbildung fertig gemacht"       │
│ Turn 3: "Als Pflegefachmann in der Charité"                   │
│ Turn 7: "Dann war ich 3 Jahre auf der Intensivstation"        │
│                                                                 │
│ Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"        │
│                                                                 │
│ → KOMBINIERE alle relevanten Turns!                            │
│ → checked: true                                                 │
│ → value: "ja (2019, Charité, 3 Jahre Intensivstation)"        │
│ → confidence: 0.95                                              │
│ → evidence: [                                                   │
│     {span: "2019 meine Ausbildung", turn_index: 1, ...},       │
│     {span: "Pflegefachmann in der Charité", turn_index: 3,...} │
│   ] (MEHRERE Evidence-Einträge!)                               │
└────────────────────────────────────────────────────────────────┘

REGELN:
1. ✅ Lies das GESAMTE Transkript für jede Qualifikationsfrage
2. ✅ KOMBINIERE Informationen aus verschiedenen Turns
3. ✅ Erstelle MEHRERE Evidence-Einträge wenn Info verteilt ist
4. ✅ Nutze Kontext: "Dann" / "Danach" / "Dort" = Bezug zu vorherigem Turn
5. ✅ Auch frühe Turns (0-5) beachten - oft wird CV zu Beginn erwähnt

❌ NICHT: Jeden Turn isoliert betrachten
❌ NICHT: Nur den ersten passenden Turn nutzen
✅ IMMER: Alle relevanten Turns zu einer Gesamtaussage kombinieren

═══════════════════════════════════════════════════════════════════
CONFIDENCE-SCORE KALIBRIERUNG (PRÄZISE!)
═══════════════════════════════════════════════════════════════════

Nutze diese GENAUE Tabelle für Confidence-Scores:

confidence: 0.95-1.0 (SEHR HOCH - Eindeutige Bestätigung):
├─ Explizite Aussage mit Zertifikat/Abschluss/Jahr
├─ "Ja, ich habe [Qualifikation] abgeschlossen in [Jahr]"
├─ Nachweis-Nummer oder Institution genannt
└─ Mehrfache Bestätigung im Transkript

confidence: 0.85-0.94 (HOCH - Starke Indizien):
├─ Explizite Bestätigung ohne Jahr/Details
├─ Mehrere Evidence-Einträge aus verschiedenen Turns
└─ Institution/Arbeitgeber genannt

confidence: 0.75-0.84 (MITTEL-HOCH - Implizite Verneinung):
├─ "Nein, aber..." mit Alternativ-Qualifikation
├─ Andere Qualifikation genannt
└─ Ausländische Ausbildung ohne Anerkennung

confidence: 0.90-0.95 (SEHR HOCH - Eindeutige Verneinung):
├─ Explizite Verneinung ohne Alternativen
├─ Komplett andere Branche
└─ "Nein, das habe ich nicht"

⚠️ Bei confidence < 0.90 → Immer ausführliche notes mit Begründung!


═══════════════════════════════════════════════════════════════════
REGELN FÜR ARBEITSZEITFRAGEN (KRITISCH)
═══════════════════════════════════════════════════════════════════

Bei Fragen zu Vollzeit/Teilzeit mit Stundenzahlen:

⚠️ WICHTIG: Wenn Kandidat konkrete Stundenzahl nennt, müssen BEIDE Fragen gefüllt werden!

BEISPIEL 1 - Kandidat nennt Stundenzahl (z.B. "35 Stunden"):
┌────────────────────────────────────────────────────────────────┐
│ Frage 1: "Vollzeit: 38,5Std/Woche" oder "Vollzeit: 40h"        │
│ Kandidat: "Ich möchte 35 Stunden arbeiten"                     │
│                                                                 │
│ → checked: false (35 ≠ 38,5)                                   │
│ → value: "nein (35h)"                                          │
│ → confidence: 0.95                                             │
│ → notes: "Kandidat will 35h (Teilzeit)"                       │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ Frage 2: "Teilzeit: flexibel" oder "Teilzeit"                  │
│ Kandidat: "Ich möchte 35 Stunden arbeiten"                     │
│                                                                 │
│ → checked: true                                                │
│ → value: "35 Stunden"                                          │
│ → confidence: 0.95                                             │
│ → notes: "Kandidat nennt konkret 35 Stunden"                  │
└────────────────────────────────────────────────────────────────┘

BEISPIEL 2 - Kandidat sagt "Vollzeit":
┌────────────────────────────────────────────────────────────────┐
│ Frage 1: "Vollzeit: 38,5Std/Woche"                             │
│ Kandidat: "Ja, Vollzeit passt mir"                             │
│                                                                 │
│ → checked: true                                                │
│ → value: "ja"                                                  │
│ → confidence: 0.95                                             │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ Frage 2: "Teilzeit: flexibel"                                  │
│ → checked: false                                               │
│ → value: "nein"                                                │
│ → confidence: 0.92                                             │
│ → notes: "Kandidat will Vollzeit"                             │
└────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════
REGELN FÜR AUSWAHLFRAGEN (KRITISCH)
═══════════════════════════════════════════════════════════════════

Fragen mit mehreren Optionen (z.B. "Station: A, B, C, D"):

⚠️ NICHT als yes_no behandeln!
✅ Als TEXT oder TEXT_LIST behandeln!
✅ IMMER den value mit der konkreten Auswahl füllen!

BEISPIEL 1 - Eine Option gewählt:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Station: Intensivstation, Geriatrie, Kardiologie, ZNA" │
│ Kandidat: "Ich möchte auf der Intensivstation arbeiten"        │
│                                                                 │
│ → checked: null (nicht relevant bei Auswahlfragen)             │
│ → value: "Intensivstation"                                     │
│ → confidence: 0.95                                             │
│ → notes: "Kandidat wählt Intensivstation"                     │
└────────────────────────────────────────────────────────────────┘

BEISPIEL 2 - Mehrere Optionen:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Station: Intensivstation, Geriatrie, Kardiologie, ZNA" │
│ Kandidat: "Intensiv oder Kardiologie wäre gut"                 │
│                                                                 │
│ → checked: null                                                │
│ → value: ["Intensivstation", "Kardiologie"]                   │
│ → confidence: 0.92                                             │
│ → notes: "Kandidat offen für 2 Stationen"                     │
└────────────────────────────────────────────────────────────────┘

BEISPIEL 3 - Flexibel/Alle:
┌────────────────────────────────────────────────────────────────┐
│ Frage: "Station: Intensivstation, Geriatrie, Kardiologie, ZNA" │
│ Kandidat: "Bin flexibel, alle Stationen ok"                    │
│                                                                 │
│ → checked: null                                                │
│ → value: "flexibel (alle Stationen)"                          │
│ → confidence: 0.88                                             │
│ → notes: "Kandidat hat keine Präferenz"                       │
└────────────────────────────────────────────────────────────────┘

KRITISCH bei Auswahlfragen:
✅ IMMER value mit konkreter Auswahl setzen!
✅ Bei Liste von Optionen in Frage → extrahiere die gewählte(n)
✅ checked bleibt null bei Auswahlfragen
❌ NICHT nur checked=true ohne value!

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


"""
Prompt-basierter Qualification Verifier.

Zwei LLM-Calls ersetzen die deterministische Qualifikationslogik:
  Prompt 1 (identify_criteria): Kriterien-Seite des Protokolls analysieren,
            echte Qualifikationskriterien von Administrativem trennen,
            begrenzt auf genau 4 Typen.
  Prompt 2 (verify_criteria): Pro Kriteriengruppe einen fokussierten
            Abgleich mit dem Transkript durchfuehren.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from models import PromptAnswer, Evidence, QualificationGroup
from llm_client import LLMClient

logger = logging.getLogger(__name__)


class QualificationVerifier:
    """
    Prueft Qualifikationskriterien prompt-basiert gegen das Transkript.

    identify_criteria() wird einmal pro Template ausgefuehrt und das
    Ergebnis in der YAML-Config gecacht. verify_criteria() laeuft
    pro Kandidat und gibt PromptAnswer-Objekte zurueck, die die
    bestehenden Extractor-Antworten ueberschreiben.
    """

    # Feste 4 Kriterientypen -- diese Beschreibungen fliessen direkt in Prompt 1
    CRITERION_TYPES = {
        "ausbildung": (
            "Berufsausbildung, Studium, Abschluss, Qualifikation, "
            "Azubi-Pfad mit Schulvoraussetzung (z.B. Haupt-/Realschulabschluss), "
            "auslaendische Anerkennung im Zusammenhang mit Qualifikation"
        ),
        "sprache": (
            "Sprachkenntnisse, Deutschkenntnisse, Sprachniveau, "
            "z.B. 'Deutsch B2', 'Deutsch C1', 'mind. B2'"
        ),
        "fuehrerschein": (
            "Fuehrerschein, Fahrerlaubnis, Fuehrerscheinklasse "
            "(z.B. Klasse B, C, CE)"
        ),
        "erfahrung": (
            "Berufserfahrung NUR mit konkreter Zeitvorgabe, "
            "z.B. 'mindestens 3 Jahre', 'X Jahre Erfahrung'"
        ),
    }

    def __init__(self, prefer_claude: bool = True):
        self.llm_client = LLMClient(prefer_claude=prefer_claude)

    # ------------------------------------------------------------------ #
    # Prompt 1: Kriterien identifizieren (einmal pro Template)
    # ------------------------------------------------------------------ #

    def identify_criteria(self, protocol: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analysiert die Kriterien-Seite des Protokoll-Templates und gibt
        qualification_groups + must_criteria im Config-Format zurueck.

        Wird einmal pro Template aufgerufen; Ergebnis wird in der
        YAML-Config gecacht.

        Args:
            protocol: Protokoll-Template (JSON dict)

        Returns:
            {
              "qualification_groups": [...],   # MandantenConfig-kompatibel
              "must_criteria": []              # immer leer (legacy-kompatibel)
            }
        """
        criteria_page = self._find_criteria_page(protocol)
        if not criteria_page:
            logger.warning("Keine Kriterien-Seite gefunden -- qualification_groups leer")
            return {"qualification_groups": [], "must_criteria": []}

        prompts = [
            p for p in criteria_page.get("prompts", [])
            if p.get("type") not in ("info", "recruiter_instruction")
        ]

        if not prompts:
            logger.warning("Kriterien-Seite hat keine auswertbaren Prompts")
            return {"qualification_groups": [], "must_criteria": []}

        prompts_json = json.dumps(
            [{"prompt_id": p["id"], "text": p.get("question", "")} for p in prompts],
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = self._build_identify_system_prompt()
        user_prompt = self._build_identify_user_prompt(prompts_json)

        try:
            response_text = self.llm_client.create_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                max_tokens=3000,
            )
            result = json.loads(response_text)
            groups_raw = result.get("qualification_groups", [])
            qualification_groups = self._convert_to_config_format(groups_raw)
            logger.info(
                f"Prompt 1: {len(qualification_groups)} Qualifikationsgruppen identifiziert"
            )
            return {"qualification_groups": qualification_groups, "must_criteria": []}

        except Exception as e:
            logger.error(f"identify_criteria fehlgeschlagen: {e}")
            return {"qualification_groups": [], "must_criteria": []}

    def _build_identify_system_prompt(self) -> str:
        types_block = "\n".join(
            f"{i+1}. {key.upper()}: {desc}"
            for i, (key, desc) in enumerate(self.CRITERION_TYPES.items())
        )
        return f"""Du analysierst die Kriterien-Seite eines Bewerbungs-Gesprächsprotokolls.

AUFGABE:
Ordne jeden Prompt einem der genau 4 Qualifikationstypen zu ODER markiere
ihn als nicht qualifikationsrelevant.

═══════════════════════════════════════════════════════════════
FESTE KRITERIENTYPEN (NUR DIESE 4):

{types_block}

NICHT QUALIFIKATIONSRELEVANT (Administratives):
- Daten erfassen: Geburtsdatum, Adresse, Staatsangehörigkeit, Personalausweis
- Dokumente: Lebenslauf erstellen, Zeugnisse anfordern
- Einwilligungen: DSGVO, Kontaktaufnahme für andere Stellen
- Systemeintragungen: JobID eintragen, Notizen
- Kommunikation: SMS-Benachrichtigung, Ansprechpartner
- Allgemeine Informationsfragen ohne Qualifikationsbezug
═══════════════════════════════════════════════════════════════

GRUPPIERUNG:
Wenn mehrere Prompts verschiedene Qualifikationsstufen ODER -pfade
für denselben Typ beschreiben (Kandidat muss NUR EINEN davon erfüllen),
fasse sie als eine OR-Gruppe zusammen.

Beispiel: "Pflegefachkraft", "Pflegehilfskraft (mit Ausbildung)",
"Pflegehelfer (ungelernt mit Erfahrung)", "Azubi PFK: Realschulabschluss"
→ alle 4 in EINER Gruppe vom Typ "ausbildung" mit logic "OR"

Antworte NUR als valides JSON ohne weiteren Text:
{{
  "qualification_groups": [
    {{
      "group_name": "beschreibender Name der Gruppe",
      "criterion_type": "ausbildung|sprache|fuehrerschein|erfahrung",
      "logic": "OR",
      "is_mandatory": true,
      "prompts": [
        {{
          "prompt_id": <int>,
          "text": "Originaltext",
          "role": "Bedeutung in der Gruppe"
        }}
      ]
    }}
  ],
  "non_qualification_prompts": [
    {{
      "prompt_id": <int>,
      "text": "...",
      "reason": "warum nicht qualifikationsrelevant"
    }}
  ]
}}"""

    def _build_identify_user_prompt(self, prompts_json: str) -> str:
        return f"""PROMPTS DER KRITERIEN-SEITE:

{prompts_json}

Analysiere jeden Prompt und erstelle qualification_groups."""

    def _convert_to_config_format(self, groups_raw: List[Dict]) -> List[Dict]:
        """Konvertiert LLM-Output in MandantenConfig-kompatibles Format."""
        result = []
        for i, group in enumerate(groups_raw):
            prompts = group.get("prompts", [])
            if not prompts:
                continue
            options = [
                {
                    "prompt_id": p["prompt_id"],
                    "description": p.get("text", "")[:100],
                    "weight": 1.0,
                }
                for p in prompts
            ]
            criterion_type = group.get("criterion_type", "ausbildung")
            result.append(
                {
                    "group_id": f"qual_group_{i + 1}",
                    "group_name": group.get("group_name", f"Qualifikation {i + 1}"),
                    "criterion_type": criterion_type,
                    "logic": group.get("logic", "OR"),
                    "options": options,
                    "min_required": 1,
                    "is_mandatory": group.get("is_mandatory", True),
                    "error_msg": (
                        f"Qualifikationskriterium nicht erfüllt: {group.get('group_name', '')}"
                    ),
                }
            )
        return result

    # ------------------------------------------------------------------ #
    # Prompt 2: Kriterien pruefen (pro Kandidat)
    # ------------------------------------------------------------------ #

    def verify_criteria(
        self,
        qualification_groups: List[QualificationGroup],
        transcript: List[Dict[str, str]],
    ) -> Dict[int, PromptAnswer]:
        """
        Prueft jede Qualifikationsgruppe fokussiert gegen das Transkript.

        Pro mandatory-Gruppe ein eigener LLM-Call mit typspezifischem Prompt.
        Das Ergebnis ueberschreibt die Antworten des Haupt-Extractors fuer
        die betroffenen Prompt-IDs.

        Args:
            qualification_groups: Aus Config geladene Gruppen
            transcript: Liste von {speaker, text} Dicts

        Returns:
            Dict {prompt_id: PromptAnswer} -- nur fuer qualifikationsrelevante Prompts
        """
        results: Dict[int, PromptAnswer] = {}

        transcript_text = self._format_transcript(transcript)

        for group in qualification_groups:
            if not group.is_mandatory and not group.options:
                continue

            criterion_type = group.criterion_type or "ausbildung"
            system_prompt = self._build_verify_system_prompt(criterion_type)
            user_prompt = self._build_verify_user_prompt(group, transcript_text)

            try:
                response_text = self.llm_client.create_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0,
                    max_tokens=1500,
                )
                response = json.loads(response_text)

                matched_prompt_id = response.get("matched_prompt_id")
                checked = response.get("checked")
                value = response.get("value")
                confidence = float(response.get("confidence", 0.8))
                notes = response.get("notes", "")

                # Ergebnis allen Prompts der Gruppe zuweisen
                for option in group.options:
                    if option.prompt_id == matched_prompt_id:
                        # Den gematchten Prompt als erfuellt markieren
                        results[option.prompt_id] = PromptAnswer(
                            checked=checked,
                            value=value,
                            confidence=confidence,
                            evidence=[
                                Evidence(
                                    span=notes[:100] if notes else "Qualification Verifier",
                                    turn_index=0,
                                    speaker="A",
                                )
                            ],
                            notes=f"[VERIFIER] {notes}",
                        )
                    elif option.prompt_id not in results:
                        # Nicht gematchte Prompts der Gruppe als nicht erfuellt markieren
                        # -- aber nur wenn ein anderer Prompt in der Gruppe gematcht hat
                        if matched_prompt_id is not None and checked is True:
                            results[option.prompt_id] = PromptAnswer(
                                checked=False,
                                value=None,
                                confidence=0.9,
                                evidence=[],
                                notes=(
                                    f"[VERIFIER] Anderer Pfad in dieser Gruppe erfuellt: "
                                    f"Prompt {matched_prompt_id}"
                                ),
                            )

                # Wenn kein spezifischer Prompt gematcht aber Gruppe als Ganzes bewertet
                if matched_prompt_id is None and checked is not None:
                    for option in group.options:
                        if option.prompt_id not in results:
                            results[option.prompt_id] = PromptAnswer(
                                checked=checked,
                                value=value,
                                confidence=confidence,
                                evidence=[
                                    Evidence(
                                        span=notes[:100] if notes else "Qualification Verifier",
                                        turn_index=0,
                                        speaker="A",
                                    )
                                ],
                                notes=f"[VERIFIER] {notes}",
                            )

                logger.info(
                    f"Verifier Gruppe '{group.group_name}': "
                    f"checked={checked}, confidence={confidence:.2f}, "
                    f"matched_prompt={matched_prompt_id}"
                )

            except Exception as e:
                logger.error(
                    f"verify_criteria fehlgeschlagen fuer Gruppe '{group.group_name}': {e}"
                )

        return results

    def _format_transcript(self, transcript: List[Dict[str, str]]) -> str:
        lines = []
        for i, turn in enumerate(transcript):
            speaker = turn.get("speaker", "?")
            text = turn.get("text", "")
            lines.append(f"[Turn {i}] {speaker}: {text}")
        return "\n".join(lines)

    def _build_verify_system_prompt(self, criterion_type: str) -> str:
        type_instructions = {
            "ausbildung": """KRITERIUMSTYP: AUSBILDUNG / QUALIFIKATION

REGELN:
- SEMANTISCHER Abgleich: Der exakte Berufstitel ist egal.
  Entscheidend ist: gleiches Berufsfeld + gleiches oder
  hoehere Ausbildungsniveau.
- Die Kriterien-Seite listet alle akzeptierten Qualifikationspfade auf
  (inkl. Azubi-Pfade). Prüfe ob der Kandidat in EINEN davon passt.
- Ein Studium im selben Fachgebiet erfüllt auch eine Ausbildungs-Anforderung.
- Berufsbezeichnungen aendern sich ueber die Jahre -- pruefe das
  Fachgebiet, nicht den Wortlaut.
- Berufserfahrung allein NICHT gleich formale Ausbildung.
- Auslaendische Ausbildung: nur mit deutscher Anerkennung gueltig
  (bei reglementierten Berufen wie Pflege, Medizin, Erziehung).
- Bei Azubi-Pfad: pruefe ob Kandidat den genannten Schulabschluss hat.
- KURZ VOR ABSCHLUSS: Kandidaten, die angeben, ihre Ausbildung
  kurz vor dem Abschluss zu stehen (z.B. "bin noch Azubi", "mache
  gerade den Abschluss", "schliesse bald ab", "im letzten Lehrjahr",
  "letztes Ausbildungsjahr", "Prüfung steht bald an"), gelten als
  QUALIFIZIERT → checked: true (confidence: 0.85).""",

            "sprache": """KRITERIUMSTYP: SPRACHKENNTNISSE

REGELN:
- Hoehere Niveaustufe erfuellt niedrigere (C1 erfuellt B2-Anforderung).
- Muttersprachler erfuellen jedes Niveau ihrer Sprache.
- Wenn das Gespraeach erkennbar fluessig auf Deutsch gefuehrt wird
  UND das Kriterium Deutsch B2 ist → implizit erfuellt (confidence: 0.80).
- Wenn Kandidat ein konkretes Niveau nennt → direkt pruefen.
- Deutliche Sprachbarrieren im Gespraeach → nicht erfuellt.""",

            "fuehrerschein": """KRITERIUMSTYP: FUEHRERSCHEIN

REGELN:
- Hoehere Klasse erfuellt niedrigere (CE erfuellt C und B).
- Kandidat muss Fuehrerschein explizit bestaetigen oder verneinen.
- Wenn Fuehrerschein im Gespraeach nicht angesprochen wird → checked: null.
- Bei Fuehrerscheinklassen: pruefe exakt die geforderte Klasse.""",

            "erfahrung": """KRITERIUMSTYP: BERUFSERFAHRUNG

REGELN:
- NUR bei konkreter Zeitvorgabe im Kriterium ist dies ein hartes Kriterium.
  Beispiel "mindestens 3 Jahre" → pruefe ob Kandidat >= 3 Jahre hat.
- OHNE Zeitvorgabe: checked: true wenn Erfahrung vorhanden (egal wie lang).
- Rechne zusammen wenn Kandidat mehrere relevante Stationen nennt.
- Im Zweifel: checked: null (nie false bei unklarer Dauer).""",
        }

        instructions = type_instructions.get(criterion_type, type_instructions["ausbildung"])

        return f"""Du pruefst EIN Qualifikationskriterium aus einem Bewerbungsgespraeach.

{instructions}

OUTPUT-SCHEMA:
Antworte NUR als valides JSON ohne weiteren Text:
{{
  "matched_prompt_id": <int oder null>,
  "checked": true|false|null,
  "value": "kurze Beschreibung der Qualifikation des Kandidaten",
  "confidence": 0.0-1.0,
  "notes": "Begruendung: warum erfuellt / warum nicht erfuellt"
}}

matched_prompt_id: ID des Prompts der am besten zur Qualifikation
des Kandidaten passt. null wenn kein spezifischer Prompt passt."""

    def _build_verify_user_prompt(
        self, group: QualificationGroup, transcript_text: str
    ) -> str:
        options_block = "\n".join(
            f"  - Prompt {opt.prompt_id}: \"{opt.description}\""
            for opt in group.options
        )
        return f"""QUALIFIKATIONSKRITERIUM: "{group.group_name}"

AKZEPTIERTE OPTIONEN (EINER reicht):
{options_block}

AUFGABE: Passt der Kandidat laut Transkript in eine dieser Optionen?

TRANSKRIPT:
{transcript_text}

Antworte NUR als JSON."""

    # ------------------------------------------------------------------ #
    # Hilfsmethoden
    # ------------------------------------------------------------------ #

    def _find_criteria_page(self, protocol: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Findet die Kriterien-Seite im Protokoll-Template."""
        for page in protocol.get("pages", []):
            page_name = page.get("name", "").lower()
            if "kriterien" in page_name or "bewerber erfüllt" in page_name or "bewerber erfuellt" in page_name:
                return page
        return None

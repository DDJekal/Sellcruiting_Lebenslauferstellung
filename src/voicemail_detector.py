"""
Transkriptbasierte Erkennung von Anrufbeantworter/Mailbox.

Wird genutzt, um den von ElevenLabs gelieferten termination_reason
bei hoher Konfidenz zu überschreiben (ElevenLabs ist oft ungenau).

Liefert außerdem immer ein call_category-Feld:
  "voicemail"     – Anrufbeantworter/Mailbox erkannt
  "agent_ended"   – KI hat regulär aufgelegt (alle Phasen oder bewusster Abbruch)
  "callee_ended"  – Gegenstelle hat aufgelegt (Gespräch nicht erfolgreich abgeschlossen)
  "unknown"       – Nicht erreicht (no-answer, busy, failed) oder unklar
"""
import re
import logging
from typing import Dict, Any, List, Literal

logger = logging.getLogger(__name__)

# Typische Phrasen in Anrufbeantworter-Ansagen (DE + EN), kleingeschrieben zum Abgleich
VOICEMAIL_PHRASES = [
    # Deutsch
    "sie haben ",
    "sie haben den",
    "sie haben die",
    "erreicht",
    "nach dem ton",
    "nach dem signal",
    "bitte hinterlassen sie",
    "hinterlassen sie eine nachricht",
    "nachricht hinterlassen",
    "nicht erreichbar",
    "derzeit nicht erreichbar",
    "momentan nicht erreichbar",
    "sprechen sie nach dem ton",
    "nach dem piepton",
    "mailbox",
    "ansage",
    "abschalten",
    "telefonnummer",
    "unter der nummer",
    "wieder anrufen",
    "rufen sie später",
    "keine antwort",
    "besetzt",
    # Englisch / international
    "leave a message",
    "after the tone",
    "after the beep",
    "voicemail",
    "voice mail",
    "not available",
    "not reachable",
    "unable to take",
    "please leave your name",
    "leave your name and number",
]

# Kompilierte Muster für schnelleren Abgleich (Wortgrenzen wo sinnvoll)
VOICEMAIL_PATTERNS = [
    re.compile(r"\bnach\s+dem\s+(ton|signal|piepton)\b", re.I),
    re.compile(r"\bhinterlassen\s+sie\s+(eine\s+)?nachricht\b", re.I),
    re.compile(r"\b(leave|hinterlassen).*message\b", re.I),
    re.compile(r"\bvoicemail\b", re.I),
    re.compile(r"\bmailbox\b", re.I),
    re.compile(r"\bnicht\s+erreichbar\b", re.I),
    re.compile(r"\bsie\s+haben\s+.+\s+erreicht\b", re.I),
]


def _call_category_from_termination_reason(termination_reason: str | None) -> str:
    """
    Leitet call_category aus dem termination_reason ab (ohne Transkript-Override).

    Returns:
        "voicemail"    – Mailbox/Anrufbeantworter
        "agent_ended"  – KI hat aufgelegt (regulär oder DSGVO/Standort-Abbruch)
        "callee_ended" – Gegenstelle hat aufgelegt
        "unknown"      – Nicht erreicht (no-answer, busy, failed) oder unklar
    """
    reason = (termination_reason or "").lower().strip()

    if not reason:
        return "unknown"

    if "voicemail" in reason:
        return "voicemail"

    if reason in ("no-answer", "busy", "failed"):
        return "unknown"

    if "call ended by remote party" in reason:
        return "callee_ended"

    if "end_call" in reason or "natural end" in reason:
        return "agent_ended"

    return "unknown"


def _text_from_speaker(transcript: List[Dict[str, str]], speaker: str) -> str:
    """Alle Texte eines Sprechers (A = Kandidat/Callee, B = Agent) konkatenieren."""
    return " ".join(
        (t.get("text") or "").strip()
        for t in transcript
        if t.get("speaker") == speaker
    ).strip()


def _count_turns(transcript: List[Dict[str, str]], speaker: str) -> int:
    """Anzahl der Turns eines Sprechers."""
    return sum(1 for t in transcript if t.get("speaker") == speaker)


def _contains_voicemail_phrases(text: str) -> bool:
    """Prüft, ob der Text typische Mailbox-Phrasen enthält."""
    if not text:
        return False
    lower = text.lower()
    for phrase in VOICEMAIL_PHRASES:
        if phrase in lower:
            return True
    for pattern in VOICEMAIL_PATTERNS:
        if pattern.search(text):
            return True
    return False


def from_transcript(
    transcript: List[Dict[str, str]],
    call_duration_secs: int = 0,
) -> Dict[str, Any]:
    """
    Erkennt anhand des Transkripts (und optional Dauer), ob es sich
    um einen Anrufbeantworter handelt.

    Args:
        transcript: Liste von {"speaker": "A"|"B", "text": "..."}
        call_duration_secs: Gesprächsdauer in Sekunden (0 = unbekannt)

    Returns:
        {
            "is_voicemail": bool,
            "confidence": "high" | "medium" | "low" | "none",
            "reason": str,
            "signals": {"phrase_match": bool, "few_turns": bool, "short_call": bool, ...}
        }
    """
    signals: Dict[str, Any] = {
        "phrase_match": False,
        "few_turns": False,
        "short_call": False,
        "user_turns": 0,
        "agent_turns": 0,
        "user_text_length": 0,
    }

    if not transcript:
        return {
            "is_voicemail": False,
            "confidence": "none",
            "reason": "empty_transcript",
            "signals": signals,
        }

    user_text = _text_from_speaker(transcript, "A")
    user_turns = _count_turns(transcript, "A")
    agent_turns = _count_turns(transcript, "B")
    total_turns = len(transcript)

    signals["user_turns"] = user_turns
    signals["agent_turns"] = agent_turns
    signals["user_text_length"] = len(user_text)

    # Phrase-Match: Kandidat (A) sagt typische Mailbox-Phrasen
    phrase_match = _contains_voicemail_phrases(user_text)
    signals["phrase_match"] = phrase_match

    # Wenige Turns: typisch für AB (Agent spricht, dann eine Ansage, Ende)
    few_turns = total_turns <= 6 and user_turns <= 2
    signals["few_turns"] = few_turns

    # Kurzer Call: unter 90 Sekunden spricht oft für AB
    short_call = call_duration_secs > 0 and call_duration_secs < 90
    signals["short_call"] = short_call

    # Starke Signale für echtes Gespräch: viele Wechsel, längere Antworten
    many_turns = total_turns >= 10 and user_turns >= 5
    long_user_content = len(user_text) > 200 and not phrase_match

    if many_turns or long_user_content:
        return {
            "is_voicemail": False,
            "confidence": "high",
            "reason": "clear_dialogue",
            "signals": signals,
        }

    if phrase_match and few_turns:
        confidence: Literal["high", "medium", "low", "none"] = "high" if short_call or user_turns <= 1 else "medium"
        return {
            "is_voicemail": True,
            "confidence": confidence,
            "reason": "voicemail_phrases_and_structure",
            "signals": signals,
        }

    if phrase_match:
        return {
            "is_voicemail": True,
            "confidence": "medium",
            "reason": "voicemail_phrases",
            "signals": signals,
        }

    if few_turns and short_call and user_turns <= 1 and len(user_text) < 50:
        return {
            "is_voicemail": True,
            "confidence": "low",
            "reason": "very_short_single_user_turn",
            "signals": signals,
        }

    return {
        "is_voicemail": False,
        "confidence": "none",
        "reason": "no_voicemail_signals",
        "signals": signals,
    }


def apply_override(
    metadata: Dict[str, Any],
    transcript: List[Dict[str, str]],
    *,
    only_high_confidence: bool = True,
) -> Dict[str, Any]:
    """
    Überschreibt termination_reason in den Metadaten, wenn die transkriptbasierte
    Erkennung mit ausreichender Konfidenz Anrufbeantworter oder echtes Gespräch erkennt.

    Setzt immer call_category, call_category_source und original_termination_reason
    (letzteres nur bei tatsächlichem Override), damit jeder Call einheitlich
    kategorisiert ist.

    Args:
        metadata: Bestehende Metadaten (z.B. von ElevenLabsTransformer.extract_metadata).
        transcript: Transkript [{"speaker":"A"|"B","text":"..."}].
        only_high_confidence: Wenn True, termination_reason nur bei confidence "high" überschreiben.

    Returns:
        Neue Metadaten-Kopie mit call_category, call_category_source (und bei Override
        auch original_termination_reason) immer gesetzt.
    """
    duration = metadata.get("call_duration_secs") or 0
    detector_result = from_transcript(transcript, call_duration_secs=duration)
    confidence = detector_result["confidence"]

    out = dict(metadata)
    original = metadata.get("termination_reason")

    # Voicemail mit ausreichender Konfidenz → termination_reason überschreiben
    if detector_result["is_voicemail"] and (not only_high_confidence or confidence == "high"):
        out["termination_reason"] = "voicemail"
        out["call_category"] = "voicemail"
        out["original_termination_reason"] = original
        out["call_category_source"] = "transcript_override"
        logger.info(
            "[VOICEMAIL-DETECTOR] termination_reason auf voicemail gesetzt (Transkript); "
            "original=%s, confidence=%s", original, confidence
        )
        return out

    # Echtes Gespräch mit hoher Konfidenz, ElevenLabs hatte aber voicemail?
    el_reason = (original or "").lower()
    if not detector_result["is_voicemail"] and confidence == "high" and "voicemail" in el_reason:
        out["termination_reason"] = "end_call tool was called."
        out["call_category"] = "agent_ended"
        out["original_termination_reason"] = original
        out["call_category_source"] = "transcript_override"
        logger.info(
            "[VOICEMAIL-DETECTOR] Voicemail-Status überschrieben → echtes Gespräch; "
            "original=%s", original
        )
        return out

    # Kein Transkript-Override – call_category aus ElevenLabs-Wert ableiten
    out["call_category"] = _call_category_from_termination_reason(original)
    out["call_category_source"] = "elevenlabs"
    # original_termination_reason nur bei Override setzen; hier kein Override
    out.setdefault("original_termination_reason", None)
    return out

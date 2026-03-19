"""WhatsApp Bot Handler – LLM-driven resume capture via chat.

Lifecycle:
1. Fallback trigger (voicemail / not reached) → Template via Meta Cloud API
2. Candidate replies → incoming message handled
3. LLM generates step-by-step responses (motivation → preferences → education → experience → closing)
4. Session completes → transcript goes through normal pipeline (Resume, Qualification, HOC)

Button-Unterstützung:
- Bestimmte Steps senden interaktive Quick-Reply-Buttons statt reinen Text
- Button-Antworten werden in menschlich lesbaren Text umgewandelt (für LLM-Kontext)
- Der LLM sieht immer Klartext – keine Button-IDs
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = int(os.getenv("WHATSAPP_SESSION_TIMEOUT_HOURS", "24"))

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "whatsapp"

STEP_PROMPT_FILES = {
    0: "wa_step0_consent.txt",
    1: "wa_step1_motivation.txt",
    2: "wa_step2_preferences.txt",
    3: "wa_step3_education.txt",
    4: "wa_step4_experience.txt",
    5: "wa_step5_closing.txt",
}

FINAL_STEP = 5

# Button-ID → lesbarer Text (für LLM-Prompt und DB-Speicherung)
BUTTON_ID_TO_TEXT: Dict[str, str] = {
    "consent_yes": "Ja, gerne",
    "consent_no": "Nein danke",
    "lang_native_yes": "Ja, Deutsch ist meine Muttersprache",
    "lang_native_no": "Nein, Deutsch ist nicht meine Muttersprache",
    "lang_b1": "B1",
    "lang_b2": "B2",
    "lang_c1": "C1",
    "lang_c2": "C2",
    "worktime_fulltime": "Vollzeit",
    "worktime_parttime": "Teilzeit",
    "worktime_both": "Beides möglich",
    "edu_loc_de": "Deutschland",
    "edu_loc_abroad": "Ausland",
    "edu_status_done": "Ja, abgeschlossen",
    "edu_status_ongoing": "Noch laufend",
    "recog_yes": "Ja, anerkannt",
    "recog_applied": "Beantragt",
    "recog_no": "Noch nicht beantragt",
    "exp_more_yes": "Ja, es gab noch eine weitere Stelle",
    "exp_more_no": "Nein, das war es",
}


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


def _resolve_button_text(message_body: str) -> str:
    """
    Wandelt eine Button-ID in lesbaren Text um.
    Falls der Text keine bekannte ID ist, wird er unverändert zurückgegeben.
    """
    return BUTTON_ID_TO_TEXT.get(message_body.strip(), message_body)


class WhatsAppHandler:
    """Handles WhatsApp bot conversations."""

    def __init__(self):
        from whatsapp_cloud_client import WhatsAppCloudClient
        self.wa_client = WhatsAppCloudClient()

        from llm_client import LLMClient
        self.llm = LLMClient(prefer_claude=True)

        self._system_prompt_cache: Optional[str] = None
        self._campaign_cache: Dict[str, Dict[str, str]] = {}

    # ─── Trigger (called by webhook_server router) ────────────────────

    async def trigger_fallback(
        self,
        metadata: Dict[str, Any],
        trigger_reason: str,
    ) -> Optional[int]:
        """
        Send initial template message and create DB session.
        Only needs name and company_name for the template.
        """
        to_number = metadata.get("to_number")
        applicant_id = metadata.get("applicant_id")
        campaign_id = metadata.get("campaign_id")

        if not to_number or not applicant_id or not campaign_id:
            logger.error(
                f"[WHATSAPP] Cannot trigger fallback: missing fields. "
                f"to={to_number}, applicant={applicant_id}, campaign={campaign_id}"
            )
            return None

        if not self.wa_client.is_configured:
            logger.error("[WHATSAPP] Cloud client not configured")
            return None

        from database import DatabaseClient

        existing = await DatabaseClient.get_active_whatsapp_session(to_number, campaign_id)
        if existing:
            logger.warning(
                f"[WHATSAPP] Active session exists for {to_number} / {campaign_id} "
                f"(id={existing['id']}). Skipping."
            )
            return existing["id"]

        session_id = await DatabaseClient.create_whatsapp_session(
            applicant_id=applicant_id,
            campaign_id=campaign_id,
            to_number=to_number,
            trigger_reason=trigger_reason,
            conversation_id=metadata.get("conversation_id"),
            candidate_first_name=metadata.get("candidate_first_name"),
            candidate_last_name=metadata.get("candidate_last_name"),
            company_name=metadata.get("company_name"),
            campaign_role_title=metadata.get("campaign_role_title"),
        )

        candidate_name = metadata.get("candidate_first_name") or "Bewerber"
        company_name = metadata.get("company_name") or "unser Unternehmen"

        from whatsapp_cloud_client import WhatsAppCloudClient
        components = WhatsAppCloudClient.build_body_components(
            name=candidate_name,
            company_name=company_name,
        )

        template_name = "sellcruiting_fallback_de"

        wamid = await self.wa_client.send_template_message(
            to_number=to_number,
            template_name=template_name,
            components=components,
        )

        if wamid:
            template_text = (
                f"Hallo {candidate_name}, ich bin Laura, die digitale "
                f"Bewerbungsassistenz von {company_name}. Wir haben versucht, "
                f"Sie telefonisch zu erreichen – leider ohne Erfolg. "
                f"Möchten Sie Ihre Bewerbung in ca. 5 Minuten per Chat "
                f"vervollständigen? Antworten Sie einfach mit \"Ja, gerne\"."
            )
            await DatabaseClient.append_whatsapp_message(
                session_id=session_id,
                role="agent",
                content=template_text,
            )
            logger.info(
                f"[WHATSAPP] Fallback triggered: session={session_id}, "
                f"to={to_number}, reason={trigger_reason}, wamid={wamid}"
            )
        else:
            logger.error(f"[WHATSAPP] Failed to send template for session {session_id}")
            await DatabaseClient.update_whatsapp_session_status(session_id, "cancelled")
            return None

        return session_id

    # ─── Incoming Message Handler ─────────────────────────────────────

    async def handle_incoming_message(
        self,
        session: Dict[str, Any],
        message_body: str,
        from_number: str,
    ) -> Optional[str]:
        """Process incoming message, generate bot response, send it."""
        session_id = session["id"]

        if self._is_session_timed_out(session):
            from database import DatabaseClient
            await DatabaseClient.update_whatsapp_session_status(session_id, "timeout")
            logger.info(f"[WHATSAPP] Session {session_id} timed out")
            return None

        from database import DatabaseClient

        # Button-IDs in lesbaren Text umwandeln, damit der LLM sinnvollen Kontext bekommt
        readable_body = _resolve_button_text(message_body)

        await DatabaseClient.append_whatsapp_message(
            session_id=session_id,
            role="user",
            content=readable_body,
        )

        logger.info(
            f"[WHATSAPP] Incoming: session={session_id}, "
            f"from={from_number}, body={readable_body[:80]}..."
        )

        # Reload session to get updated messages list
        session = await DatabaseClient.get_whatsapp_session(session_id)
        if not session:
            return None

        response_text, new_step, session_complete = await self._generate_response(session)

        if new_step is not None and new_step != session.get("current_step", 0):
            await DatabaseClient.update_whatsapp_step(session_id, new_step)

        if response_text:
            # Interaktive Nachricht (Buttons) oder plain text senden
            wamid = await self._send_response(
                to_number=session["to_number"],
                response_text=response_text,
                new_step=new_step if new_step is not None else session.get("current_step", 0),
                session=session,
            )
            if wamid:
                await DatabaseClient.append_whatsapp_message(
                    session_id=session_id,
                    role="agent",
                    content=response_text,
                )
            else:
                logger.error(f"[WHATSAPP] Failed to send response for session {session_id}")

        if session_complete:
            await self._complete_session(session_id)

        return response_text

    # ─── Response Sending (Text oder Buttons) ─────────────────────────

    async def _send_response(
        self,
        to_number: str,
        response_text: str,
        new_step: int,
        session: Dict[str, Any],
    ) -> Optional[str]:
        """
        Sendet die Bot-Antwort – je nach Step als Freitext oder mit Buttons.

        Buttons werden NACH der LLM-Antwort als separate Nachricht gesendet,
        damit der Konversationsfluss natürlich bleibt (Text zuerst, dann Auswahl).
        """
        from whatsapp_cloud_client import WhatsAppCloudClient

        # Zuerst immer den Text senden
        wamid = await self.wa_client.send_text_message(
            to_number=to_number,
            body=response_text,
        )

        if not wamid:
            return None

        # Dann ggf. passende Buttons als Folgenachricht
        button_wamid = await self._maybe_send_buttons(
            to_number=to_number,
            step=new_step,
            session=session,
        )
        if button_wamid:
            logger.info(f"[WHATSAPP] Buttons sent for step={new_step}, wamid={button_wamid}")

        return wamid

    async def _maybe_send_buttons(
        self,
        to_number: str,
        step: int,
        session: Dict[str, Any],
    ) -> Optional[str]:
        """
        Sendet passende interaktive Buttons für den aktuellen Step – aber nur einmal pro Frage.

        Logik: Buttons werden nur gesendet wenn die zugehörige Button-Antwort noch nicht
        in der Nachrichtenhistorie vorhanden ist. So wird vermieden dass dieselbe Frage
        nach jeder Antwort im gleichen Step wiederholt wird.

        - Step 1 → Muttersprache Ja/Nein (nur wenn noch keine Antwort)
        - Step 1 + Nein Muttersprache → Sprachniveau-Liste (nur wenn noch kein Niveau gewählt)
        - Step 2 → Vollzeit/Teilzeit (nur wenn noch keine Antwort)
        - Step 3 → Ausbildungsort (nur wenn noch keine Antwort)
        - Step 3 + Ausland → Anerkennungsstatus (nur wenn noch keine Antwort)
        - Step 3 + Ort/Anerkennung bekannt → Abschluss-Status (nur wenn noch keine Antwort)
        - Step 4 → Weitere Arbeitsstation (nur wenn noch keine Antwort)
        """
        from whatsapp_cloud_client import WhatsAppCloudClient

        messages = session.get("messages") or []
        if isinstance(messages, str):
            messages = json.loads(messages)

        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        last_user_msg = user_msgs[-1] if user_msgs else ""

        # Hilfsfunktion: prüft ob eine der bekannten Antworten bereits in der Historie ist
        def already_answered(*known_answers: str) -> bool:
            return any(ans in user_msgs for ans in known_answers)

        # Step 1: Muttersprache-Frage
        if step == 1:
            native_answers = (
                "Ja, Deutsch ist meine Muttersprache",
                "Nein, Deutsch ist nicht meine Muttersprache",
            )
            level_answers = ("B1", "B2", "C1", "C2")

            # Sprachniveau-Liste: nur wenn "Nein" gewählt aber noch kein Niveau
            if already_answered(*native_answers):
                if last_user_msg in ("Nein, Deutsch ist nicht meine Muttersprache",) \
                        and not already_answered(*level_answers):
                    body, button_label, sections = WhatsAppCloudClient.list_language_level()
                    return await self.wa_client.send_list_message(
                        to_number=to_number,
                        body=body,
                        button_label=button_label,
                        sections=sections,
                    )
                # Muttersprache bereits beantwortet → keine weiteren Buttons für Step 1
                return None

            # Noch keine Antwort → Muttersprache Ja/Nein fragen
            body, buttons = WhatsAppCloudClient.buttons_german_native()
            return await self.wa_client.send_button_message(
                to_number=to_number,
                body=body,
                buttons=buttons,
            )

        # Step 2: Vollzeit/Teilzeit – nur wenn noch keine Antwort
        if step == 2:
            if already_answered("Vollzeit", "Teilzeit", "Beides möglich"):
                return None
            body, buttons = WhatsAppCloudClient.buttons_fulltime_parttime()
            return await self.wa_client.send_button_message(
                to_number=to_number,
                body=body,
                buttons=buttons,
            )

        # Step 3: Ausbildung
        if step == 3:
            edu_loc_answers = ("Deutschland", "Ausland")
            recog_answers = ("Ja, anerkannt", "Beantragt", "Noch nicht beantragt")
            edu_status_answers = ("Ja, abgeschlossen", "Noch laufend")

            # Anerkennungsstatus: nur wenn Ausland gewählt aber noch keine Anerkennungsantwort
            if already_answered("Ausland") and not already_answered(*recog_answers):
                body, buttons = WhatsAppCloudClient.buttons_recognition_status()
                return await self.wa_client.send_button_message(
                    to_number=to_number,
                    body=body,
                    buttons=buttons,
                )

            # Abschluss-Status: nur wenn Ort (und ggf. Anerkennung) bekannt aber noch kein Status
            if already_answered(*edu_loc_answers) and not already_answered(*edu_status_answers):
                # Bei Ausland: erst Anerkennung abwarten
                if already_answered("Ausland") and not already_answered(*recog_answers):
                    return None
                body, buttons = WhatsAppCloudClient.buttons_education_status()
                return await self.wa_client.send_button_message(
                    to_number=to_number,
                    body=body,
                    buttons=buttons,
                )

            # Ausbildungsort noch nicht bekannt → fragen
            if not already_answered(*edu_loc_answers):
                body, buttons = WhatsAppCloudClient.buttons_education_location()
                return await self.wa_client.send_button_message(
                    to_number=to_number,
                    body=body,
                    buttons=buttons,
                )

            # Alle Step-3-Fragen beantwortet
            return None

        # Step 4: Weitere Arbeitsstation – nur wenn noch keine Antwort
        if step == 4:
            if already_answered("Ja, es gab noch eine weitere Stelle", "Nein, das war es"):
                return None
            body, buttons = WhatsAppCloudClient.buttons_more_experience()
            return await self.wa_client.send_button_message(
                to_number=to_number,
                body=body,
                buttons=buttons,
            )

        return None

    # ─── LLM Response Generation ─────────────────────────────────────

    async def _generate_response(
        self,
        session: Dict[str, Any],
    ) -> Tuple[str, Optional[int], bool]:
        """
        Generate bot response based on current step and conversation history.

        Returns: (response_text, new_step, session_complete)
        """
        current_step = session.get("current_step", 0)
        messages = session.get("messages") or []
        if isinstance(messages, str):
            messages = json.loads(messages)

        system_prompt = self._build_system_prompt(session, current_step)
        user_prompt = self._build_user_prompt(messages)

        try:
            raw = self.llm.create_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1000,
            )

            result = self._parse_llm_response(raw)
        except Exception as e:
            logger.error(f"[WHATSAPP] LLM error: {e}", exc_info=True)
            return (
                "Entschuldigung, es gab ein technisches Problem. "
                "Bitte versuchen Sie es in einer Minute nochmal.",
                None,
                False,
            )

        response_text = result.get("response", "")
        step_complete = result.get("step_complete", False)
        session_complete = result.get("session_complete", False)

        # Step 0: Einverständnis
        if current_step == 0:
            consent = result.get("consent")
            if consent is True:
                return response_text, 1, False
            elif consent is False:
                return response_text, None, True
            else:
                return response_text, None, False

        new_step = current_step
        if step_complete and current_step < FINAL_STEP:
            new_step = current_step + 1
        elif step_complete and current_step == FINAL_STEP:
            session_complete = True

        return response_text, new_step, session_complete

    def _build_system_prompt(self, session: Dict[str, Any], step: int) -> str:
        """Build full system prompt: master + step-specific + campaign context."""
        if not self._system_prompt_cache:
            self._system_prompt_cache = _load_prompt("wa_system_prompt.txt")

        step_file = STEP_PROMPT_FILES.get(step)
        step_prompt = _load_prompt(step_file) if step_file else ""

        campaign_id = session.get("campaign_id", "")
        gate_q, pref_q = self._get_campaign_questions(campaign_id)

        step_prompt = step_prompt.replace("{gate_questions}", gate_q)
        step_prompt = step_prompt.replace("{preference_questions}", pref_q)

        context = (
            f"\n\nKONTEXT:\n"
            f"- Bewerber: {session.get('candidate_first_name', '?')} {session.get('candidate_last_name', '?')}\n"
            f"- Firma: {session.get('company_name', '?')}\n"
            f"- Stelle: {session.get('campaign_role_title', '?')}\n"
            f"- Aktueller Step: {step}\n"
            f"\nHINWEIS: Der Bewerber kann Antworten per Button-Auswahl oder Freitext senden. "
            f"Button-Antworten wurden bereits in Klartext umgewandelt."
        )

        return self._system_prompt_cache + "\n\n" + step_prompt + context

    def _build_user_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert message history to a chat transcript for the LLM."""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                continue
            label = "BEWERBER" if role == "user" else "LAURA"
            lines.append(f"{label}: {content}")

        return "\n".join(lines) if lines else "(Noch keine Nachrichten)"

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        """Parse LLM JSON response, with fallback to plain text."""
        raw = raw.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"response": raw, "step_complete": False}

    def _get_campaign_questions(self, campaign_id: str) -> tuple:
        """
        Load gate_questions and preference_questions for a campaign.
        Fetches from HOC API via QuestionnaireClient, caches per campaign.

        Returns: (gate_questions_text, preference_questions_text)
        """
        if campaign_id in self._campaign_cache:
            cached = self._campaign_cache[campaign_id]
            return cached.get("gate", ""), cached.get("pref", "")

        gate_text = "(Keine Gate-Fragen vorhanden)"
        pref_text = "(Keine Präferenzfragen vorhanden)"

        if not campaign_id:
            return gate_text, pref_text

        try:
            from questionnaire_client import QuestionnaireClient
            client = QuestionnaireClient()
            protocol = client.get_questionnaire_sync(campaign_id)

            gate_text, pref_text = self._extract_questions_from_protocol(protocol)
        except Exception as e:
            logger.warning(f"[WHATSAPP] Could not load campaign questions for {campaign_id}: {e}")

        self._campaign_cache[campaign_id] = {"gate": gate_text, "pref": pref_text}
        return gate_text, pref_text

    @staticmethod
    def _extract_questions_from_protocol(protocol: Dict[str, Any]) -> tuple:
        """
        Extract gate and preference questions from the HOC protocol JSON.
        The protocol contains pages with questions; we classify by page type
        (interest = gate, action = preference).
        """
        pages = protocol.get("pages") or []
        gate_parts: List[str] = []
        pref_parts: List[str] = []

        for page in pages:
            page_type = (page.get("page_type") or "").lower()
            questions = page.get("questions") or []

            for q in questions:
                q_text = q.get("text") or q.get("question") or ""
                if not q_text:
                    continue
                q_type = (q.get("type") or "").upper()
                options = q.get("options") or []
                option_str = ", ".join(
                    o.get("text", "") for o in options if o.get("text")
                )

                line = f"- [{q_type}] {q_text}"
                if option_str:
                    line += f" (Optionen: {option_str})"

                if page_type in ("interest", "gate", "must"):
                    gate_parts.append(line)
                elif page_type in ("action", "preference", "wish"):
                    pref_parts.append(line)

        gate = "\n".join(gate_parts) if gate_parts else "(Keine Gate-Fragen vorhanden)"
        pref = "\n".join(pref_parts) if pref_parts else "(Keine Präferenzfragen vorhanden)"
        return gate, pref

    # ─── Session Completion ───────────────────────────────────────────

    async def _complete_session(self, session_id: int) -> None:
        """Mark session completed and trigger pipeline processing."""
        from database import DatabaseClient
        await DatabaseClient.update_whatsapp_session_status(session_id, "completed")
        logger.info(f"[WHATSAPP] Session {session_id} completed, starting pipeline...")

        try:
            from pipeline_processor import PipelineProcessor
            processor = PipelineProcessor()
            await processor.process_whatsapp_session(session_id)
        except Exception as e:
            logger.error(
                f"[WHATSAPP] Pipeline error for session {session_id}: {e}",
                exc_info=True,
            )

    # ─── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _is_session_timed_out(session: Dict[str, Any]) -> bool:
        last_message = session.get("last_message_at")
        if not last_message:
            last_message = session.get("created_at")
        if not last_message:
            return False
        if isinstance(last_message, str):
            last_message = datetime.fromisoformat(last_message)

        timeout = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
        return last_message < timeout

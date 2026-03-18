"""Meta WhatsApp Cloud API Client.

Communicates directly with the Meta Graph API for sending and receiving
WhatsApp messages. Replaces Twilio for WhatsApp operations.

API docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import os
import hashlib
import hmac
import logging
from typing import Dict, Any, Optional, List

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"


class WhatsAppCloudClient:
    """Client for Meta WhatsApp Cloud API."""

    def __init__(self):
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
        self.verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        self.api_version = os.getenv("WHATSAPP_API_VERSION", "v22.0")
        self.template_name = os.getenv("WHATSAPP_TEMPLATE_NAME", "")
        self.app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
        self.waba_id = os.getenv("WHATSAPP_WABA_ID", "")

        if not all([self.phone_number_id, self.api_token]):
            logger.warning(
                "WhatsApp Cloud API not fully configured. "
                "Set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_API_TOKEN."
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.api_token)

    @property
    def _messages_url(self) -> str:
        return f"{GRAPH_API_BASE}/{self.api_version}/{self.phone_number_id}/messages"

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    # ─── Outgoing Messages ───────────────────────────────────────────

    async def send_template_message(
        self,
        to_number: str,
        template_name: Optional[str] = None,
        language_code: str = "de",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """
        Send a pre-approved template message (initiates conversation).

        Args:
            to_number: Recipient in international format without '+' (e.g. 4915204465582)
            template_name: Meta-approved template name. Falls back to env WHATSAPP_TEMPLATE_NAME.
            language_code: Template language (default: de)
            components: Template components with parameter values, e.g.
                [{"type": "body", "parameters": [{"type": "text", "text": "Max"}, ...]}]

        Returns:
            WhatsApp message ID (wamid) on success, None on error.
        """
        if not self.is_configured:
            logger.error("[WA-CLOUD] Client not configured")
            return None

        tpl = template_name or self.template_name
        if not tpl:
            logger.error("[WA-CLOUD] No template name provided")
            return None

        to_clean = to_number.lstrip("+").replace(" ", "")

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "template",
            "template": {
                "name": tpl,
                "language": {"code": language_code},
            },
        }

        if components:
            payload["template"]["components"] = components

        return await self._send(payload)

    async def send_text_message(
        self,
        to_number: str,
        body: str,
    ) -> Optional[str]:
        """
        Send a freeform text message (within 24h conversation window).

        Args:
            to_number: Recipient in international format without '+'
            body: Message text

        Returns:
            WhatsApp message ID (wamid) on success, None on error.
        """
        if not self.is_configured:
            logger.error("[WA-CLOUD] Client not configured")
            return None

        to_clean = to_number.lstrip("+").replace(" ", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "text",
            "text": {"body": body},
        }

        return await self._send(payload)

    async def _send(self, payload: Dict[str, Any]) -> Optional[str]:
        """Send payload to Messages API, return wamid or None."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    self._messages_url,
                    headers=self._headers,
                    json=payload,
                )

                if resp.status_code not in (200, 201):
                    logger.error(
                        f"[WA-CLOUD] API error {resp.status_code}: {resp.text}"
                    )
                    return None

                data = resp.json()
                wamid = (data.get("messages") or [{}])[0].get("id")
                logger.info(f"[WA-CLOUD] Message sent: wamid={wamid}")
                return wamid

        except Exception as e:
            logger.error(f"[WA-CLOUD] Send failed: {e}", exc_info=True)
            return None

    # ─── Incoming Messages (Webhook) ─────────────────────────────────

    def verify_webhook(self, params: Dict[str, str]) -> Optional[str]:
        """
        Handle Meta webhook verification (GET request).

        Args:
            params: Query parameters from the GET request

        Returns:
            hub.challenge value if verification succeeds, None otherwise.
        """
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            logger.info("[WA-CLOUD] Webhook verified")
            return challenge

        logger.warning(
            f"[WA-CLOUD] Webhook verification failed: mode={mode}, "
            f"token_match={token == self.verify_token}"
        )
        return None

    def validate_signature(self, body: bytes, signature_header: str) -> bool:
        """
        Validate X-Hub-Signature-256 from Meta webhook POST.

        Args:
            body: Raw request body bytes
            signature_header: Value of X-Hub-Signature-256 header

        Returns:
            True if signature is valid.
        """
        if not self.app_secret:
            logger.warning("[WA-CLOUD] No app_secret configured, skipping signature check")
            return True

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(
            self.app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header[7:])

    @staticmethod
    def parse_incoming_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract messages from Meta webhook payload.

        Handles both plain text messages and interactive button replies.
        For button replies, the button ID is returned as message_body so the
        handler can resolve it to human-readable text via BUTTON_ID_TO_TEXT.

        Args:
            payload: Full JSON body from POST /whatsapp/webhook

        Returns:
            List of dicts with keys: from_number, message_body, message_id, timestamp
        """
        messages = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    msg_type = msg.get("type")
                    from_number = msg.get("from", "")
                    message_id = msg.get("id", "")
                    timestamp = msg.get("timestamp", "")

                    if msg_type == "text":
                        body = (msg.get("text") or {}).get("body", "")
                    elif msg_type == "interactive":
                        # Button-Reply: ID als body zurückgeben
                        interactive = msg.get("interactive") or {}
                        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                        body = reply.get("id", "")
                    else:
                        continue

                    if not body:
                        continue

                    messages.append({
                        "from_number": from_number,
                        "message_body": body,
                        "message_id": message_id,
                        "timestamp": timestamp,
                    })

        return messages

    # ─── Interactive Messages ─────────────────────────────────────────

    async def send_button_message(
        self,
        to_number: str,
        body: str,
        buttons: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Send an interactive message with Quick Reply buttons (max. 3).

        Args:
            to_number: Recipient in international format without '+'
            body: Message body text
            buttons: List of dicts with 'id' and 'title' keys.
                     Example: [{"id": "yes", "title": "Ja, gerne"}]

        Returns:
            WhatsApp message ID (wamid) on success, None on error.
        """
        if not self.is_configured:
            logger.error("[WA-CLOUD] Client not configured")
            return None

        to_clean = to_number.lstrip("+").replace(" ", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn["id"],
                                "title": btn["title"][:20],  # Meta limit: 20 chars
                            },
                        }
                        for btn in buttons[:3]  # Meta limit: max 3 buttons
                    ]
                },
            },
        }

        return await self._send(payload)

    async def send_list_message(
        self,
        to_number: str,
        body: str,
        button_label: str,
        sections: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Send an interactive list message (up to 10 options).

        Args:
            to_number: Recipient in international format without '+'
            body: Message body text
            button_label: Label on the list-open button (max. 20 chars)
            sections: List of section dicts:
                [{"title": "Abschnitt", "rows": [{"id": "b1", "title": "B1", "description": "..."}]}]

        Returns:
            WhatsApp message ID (wamid) on success, None on error.
        """
        if not self.is_configured:
            logger.error("[WA-CLOUD] Client not configured")
            return None

        to_clean = to_number.lstrip("+").replace(" ", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_label[:20],
                    "sections": sections,
                },
            },
        }

        return await self._send(payload)

    # ─── Template Management (Meta Graph API) ────────────────────────

    async def create_template(
        self,
        name: str,
        body_text: str,
        example_values: List[str],
        category: str = "UTILITY",
        language: str = "de",
        buttons: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Submit a new message template to Meta for approval.

        Requires WHATSAPP_WABA_ID to be set.

        Args:
            name: Template name (lowercase, underscores only, e.g. 'sellcruiting_fallback_de')
            body_text: Template body with {{1}}, {{2}} placeholders
            example_values: Example values for placeholders, e.g. ["Max", "Caritas GmbH"]
            category: "UTILITY" (transactional) or "MARKETING"
            language: Language code, e.g. "de"
            buttons: Optional Quick Reply buttons:
                [{"type": "QUICK_REPLY", "text": "Ja, gerne"}]

        Returns:
            API response dict with 'id' and 'status', or None on error.
        """
        if not self.waba_id:
            logger.error("[WA-CLOUD] WHATSAPP_WABA_ID not configured")
            return None
        if not self.api_token:
            logger.error("[WA-CLOUD] WHATSAPP_API_TOKEN not configured")
            return None

        url = f"{GRAPH_API_BASE}/{self.api_version}/{self.waba_id}/message_templates"

        components: List[Dict[str, Any]] = [
            {
                "type": "BODY",
                "text": body_text,
                "example": {
                    "body_text": [example_values],
                },
            }
        ]

        if buttons:
            components.append({
                "type": "BUTTONS",
                "buttons": buttons,
            })

        payload = {
            "name": name,
            "language": language,
            "category": category,
            "components": components,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers=self._headers,
                    json=payload,
                )
                data = resp.json()

                if resp.status_code not in (200, 201):
                    logger.error(
                        f"[WA-CLOUD] Template creation failed {resp.status_code}: {data}"
                    )
                    return None

                logger.info(
                    f"[WA-CLOUD] Template submitted: name={name}, "
                    f"id={data.get('id')}, status={data.get('status')}"
                )
                return data

        except Exception as e:
            logger.error(f"[WA-CLOUD] Template creation error: {e}", exc_info=True)
            return None

    async def get_template_status(
        self,
        template_name: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch approval status of message templates from Meta.

        Args:
            template_name: Filter by specific template name. If None, returns all.

        Returns:
            List of template dicts with 'name', 'status', 'id', or None on error.
        """
        if not self.waba_id:
            logger.error("[WA-CLOUD] WHATSAPP_WABA_ID not configured")
            return None

        url = f"{GRAPH_API_BASE}/{self.api_version}/{self.waba_id}/message_templates"
        params = {"fields": "name,status,id,language,category,components"}
        if template_name:
            params["name"] = template_name

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    headers=self._headers,
                    params=params,
                )
                data = resp.json()

                if resp.status_code != 200:
                    logger.error(
                        f"[WA-CLOUD] Template status fetch failed {resp.status_code}: {data}"
                    )
                    return None

                templates = data.get("data", [])
                logger.info(f"[WA-CLOUD] Fetched {len(templates)} templates")
                return templates

        except Exception as e:
            logger.error(f"[WA-CLOUD] Template status error: {e}", exc_info=True)
            return None

    # ─── Template Helper ─────────────────────────────────────────────

    @staticmethod
    def build_body_components(
        name: str,
        company_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Build template components for the initial fallback message.
        Template variables: {{1}} = name, {{2}} = company_name.
        """
        return [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": name},
                    {"type": "text", "text": company_name},
                ],
            }
        ]

    # ─── Interactive Message Payloads (vorgefertigte Step-Vorlagen) ───

    @staticmethod
    def buttons_consent() -> tuple:
        """Step 0: Einverständnis – Ja/Nein Buttons."""
        return (
            "Möchten Sie jetzt starten?",
            [
                {"id": "consent_yes", "title": "Ja, gerne ✓"},
                {"id": "consent_no", "title": "Nein danke"},
            ],
        )

    @staticmethod
    def buttons_german_native() -> tuple:
        """Step 1: Ist Deutsch Ihre Muttersprache?"""
        return (
            "Ist Deutsch Ihre Muttersprache?",
            [
                {"id": "lang_native_yes", "title": "Ja, Muttersprache"},
                {"id": "lang_native_no", "title": "Nein, Fremdsprache"},
            ],
        )

    @staticmethod
    def list_language_level() -> tuple:
        """Step 1: Sprachniveau (wenn kein Muttersprachler)."""
        body = "Welches Deutschniveau haben Sie ungefähr?"
        button_label = "Niveau wählen"
        sections = [
            {
                "title": "Sprachniveau",
                "rows": [
                    {"id": "lang_b1", "title": "B1", "description": "Mittelstufe – einfache Gespräche"},
                    {"id": "lang_b2", "title": "B2", "description": "Gute Kenntnisse – flüssige Kommunikation"},
                    {"id": "lang_c1", "title": "C1", "description": "Sehr gut – nahezu fließend"},
                    {"id": "lang_c2", "title": "C2", "description": "Muttersprachliches Niveau"},
                ],
            }
        ]
        return body, button_label, sections

    @staticmethod
    def buttons_fulltime_parttime() -> tuple:
        """Step 2: Vollzeit oder Teilzeit?"""
        return (
            "Suchen Sie eine Vollzeit- oder Teilzeitstelle?",
            [
                {"id": "worktime_fulltime", "title": "Vollzeit"},
                {"id": "worktime_parttime", "title": "Teilzeit"},
                {"id": "worktime_both", "title": "Beides möglich"},
            ],
        )

    @staticmethod
    def buttons_education_location() -> tuple:
        """Step 3: Ausbildung in Deutschland oder Ausland?"""
        return (
            "Haben Sie Ihre Ausbildung in Deutschland oder im Ausland absolviert?",
            [
                {"id": "edu_loc_de", "title": "Deutschland"},
                {"id": "edu_loc_abroad", "title": "Ausland"},
            ],
        )

    @staticmethod
    def buttons_education_status() -> tuple:
        """Step 3: Ausbildung abgeschlossen oder laufend?"""
        return (
            "Ist Ihre Ausbildung bereits abgeschlossen?",
            [
                {"id": "edu_status_done", "title": "Ja, abgeschlossen"},
                {"id": "edu_status_ongoing", "title": "Noch laufend"},
            ],
        )

    @staticmethod
    def buttons_recognition_status() -> tuple:
        """Step 3: Anerkennungsstatus bei ausländischem Abschluss."""
        return (
            "Wurde Ihr Abschluss in Deutschland anerkannt?",
            [
                {"id": "recog_yes", "title": "Ja, anerkannt"},
                {"id": "recog_applied", "title": "Beantragt"},
                {"id": "recog_no", "title": "Noch nicht beantragt"},
            ],
        )

    @staticmethod
    def buttons_more_experience() -> tuple:
        """Step 4: Weitere Arbeitsstation?"""
        return (
            "Gab es davor noch eine weitere relevante Stelle?",
            [
                {"id": "exp_more_yes", "title": "Ja, noch eine"},
                {"id": "exp_more_no", "title": "Nein, das war es"},
            ],
        )

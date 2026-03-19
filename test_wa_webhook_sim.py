"""
Simuliert eine eingehende WhatsApp-Nachricht direkt an den Render-Webhook.
Testet den gesamten Bot-Flow ohne echte Meta-Ereignisse.
"""
import asyncio
import sys
import json
import hmac
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv()

import httpx
import os

RENDER_URL = "https://sellcruiting-lebenslauferstellung-v3.onrender.com"
FROM_NUMBER = "4915204465582"
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "").strip()


def build_payload(message_text: str, wamid: str = "wamid.test123456789") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1443362067587947",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15550783881",
                        "phone_number_id": "1042982108897017"
                    },
                    "contacts": [{
                        "profile": {"name": "David Jekal"},
                        "wa_id": FROM_NUMBER
                    }],
                    "messages": [{
                        "from": FROM_NUMBER,
                        "id": wamid,
                        "timestamp": "1742000000",
                        "text": {"body": message_text},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }


def sign_payload(body_bytes: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def simulate_message(message_text: str, target: str = "render") -> None:
    payload = build_payload(message_text)
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()

    headers = {"Content-Type": "application/json"}
    if APP_SECRET:
        headers["X-Hub-Signature-256"] = sign_payload(body_bytes, APP_SECRET)
        print(f"✅ Signatur gesetzt (App Secret vorhanden)")
    else:
        print("⚠️  Kein APP_SECRET – Signatur wird nicht gesetzt (Webhook akzeptiert trotzdem)")

    if target == "local":
        url = "http://localhost:8000/whatsapp/webhook"
    else:
        url = f"{RENDER_URL}/whatsapp/webhook"

    print(f"\n📤 Sende simulierte Nachricht an: {url}")
    print(f"   Von:      {FROM_NUMBER}")
    print(f"   Nachricht: {message_text}")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, content=body_bytes, headers=headers)
        print(f"\n📥 Antwort: HTTP {r.status_code}")
        print(f"   Body: {r.text}")

        if r.status_code == 200:
            print("\n✅ Webhook hat die Nachricht akzeptiert.")
            print("   Prüfe die Render-Logs ob der Bot geantwortet hat.")
        elif r.status_code == 403:
            print("\n❌ Signatur-Fehler – APP_SECRET stimmt nicht überein")
        else:
            print(f"\n❌ Unerwarteter Status: {r.status_code}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="WhatsApp Webhook Simulator")
    parser.add_argument("--msg", default="Ja, gerne", help="Nachricht die simuliert wird")
    parser.add_argument("--local", action="store_true", help="Lokalen Server testen (localhost:8000)")
    args = parser.parse_args()

    target = "local" if args.local else "render"
    asyncio.run(simulate_message(args.msg, target))


if __name__ == "__main__":
    main()

"""
Test-Skript: WhatsApp Bot-Konversation initiieren.

Dieses Skript simuliert einen nicht-erreichten ElevenLabs-Anruf:
1. Legt eine WhatsApp-Session in der Datenbank an
2. Schickt das Template an die Testnummer
3. Der Bot ist danach aktiv und antwortet auf eingehende Nachrichten

Verwendung:
    python test_wa_trigger.py
    python test_wa_trigger.py --number 4915212345678
    python test_wa_trigger.py --name "Max" --company "Caritas GmbH"
"""
import asyncio
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dotenv import load_dotenv
load_dotenv()


async def trigger_test_conversation(
    to_number: str,
    candidate_first_name: str,
    candidate_last_name: str,
    company_name: str,
    campaign_id: str,
    applicant_id: str,
    trigger_reason: str,
) -> None:
    """Initiiert eine Test-WhatsApp-Konversation direkt über den WhatsAppHandler."""

    print(f"\n🚀 Starte Test-Konversation")
    print(f"   Nummer:    {to_number}")
    print(f"   Bewerber:  {candidate_first_name} {candidate_last_name}")
    print(f"   Firma:     {company_name}")
    print(f"   Grund:     {trigger_reason}")

    # Prüfe ob WhatsApp konfiguriert ist
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    api_token = os.getenv("WHATSAPP_API_TOKEN", "").strip()
    db_url = os.getenv("DATABASE_URL", "").strip()

    if not phone_id or not api_token:
        print("\n❌ WHATSAPP_PHONE_NUMBER_ID oder WHATSAPP_API_TOKEN fehlt in .env")
        return

    if not db_url:
        print("\n❌ DATABASE_URL fehlt in .env")
        return

    print(f"\n✅ Konfiguration OK")
    print(f"   Phone Number ID: {phone_id}")
    print(f"   Template:        {os.getenv('WHATSAPP_TEMPLATE_NAME', '(nicht gesetzt)')}")

    metadata = {
        "to_number": to_number,
        "applicant_id": applicant_id,
        "campaign_id": campaign_id,
        "candidate_first_name": candidate_first_name,
        "candidate_last_name": candidate_last_name,
        "company_name": company_name,
        "campaign_role_title": "Pflegefachkraft",
        "conversation_id": f"test_{applicant_id}",
        "termination_reason": trigger_reason,
    }

    try:
        from database import DatabaseClient
        from whatsapp_handler import WhatsAppHandler

        print("\n📡 Verbinde mit Datenbank...")
        await DatabaseClient.init_tables()
        print("✅ Datenbank bereit")

        handler = WhatsAppHandler()
        print("\n📤 Sende Template-Nachricht...")

        session_id = await handler.trigger_fallback(
            metadata=metadata,
            trigger_reason=trigger_reason,
        )

        if session_id:
            print(f"\n✅ Erfolgreich!")
            print(f"   Session-ID: {session_id}")
            print(f"   Template wurde an {to_number} gesendet")
            print(f"\n💬 Bot ist jetzt aktiv.")
            print(f"   Antworte auf die WhatsApp-Nachricht um das Gespräch zu starten.")
            print(f"   Der Bot antwortet sobald deine Antwort über den Webhook eingeht.")
        else:
            print(f"\n❌ Konversation konnte nicht gestartet werden.")
            print(f"   Mögliche Ursachen:")
            print(f"   - Template '{os.getenv('WHATSAPP_TEMPLATE_NAME')}' nicht genehmigt")
            print(f"   - API Token abgelaufen")
            print(f"   - Nummer {to_number} ist keine registrierte Testnummer")

    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            from database import DatabaseClient
            await DatabaseClient.close_pool()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="WhatsApp Test-Konversation initiieren",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python test_wa_trigger.py
  python test_wa_trigger.py --number 4915212345678
  python test_wa_trigger.py --name "Anna" --lastname "Muster" --company "Caritas GmbH"
  python test_wa_trigger.py --reason busy
        """,
    )
    parser.add_argument(
        "--number",
        default="4915204465582",
        help="Ziel-Telefonnummer ohne + (default: 4915204465582)",
    )
    parser.add_argument(
        "--name",
        default="Test",
        help="Vorname des Testbewerbers (default: Test)",
    )
    parser.add_argument(
        "--lastname",
        default="Bewerber",
        help="Nachname des Testbewerbers (default: Bewerber)",
    )
    parser.add_argument(
        "--company",
        default="High Office sellcruiting",
        help="Firmenname (default: High Office sellcruiting)",
    )
    parser.add_argument(
        "--campaign",
        default="test_campaign_001",
        help="Campaign-ID (default: test_campaign_001)",
    )
    parser.add_argument(
        "--applicant",
        default="test_applicant_001",
        help="Bewerber-ID (default: test_applicant_001)",
    )
    parser.add_argument(
        "--reason",
        default="voicemail",
        choices=["voicemail", "no-answer", "busy", "failed"],
        help="Trigger-Grund (default: voicemail)",
    )

    args = parser.parse_args()

    asyncio.run(trigger_test_conversation(
        to_number=args.number,
        candidate_first_name=args.name,
        candidate_last_name=args.lastname,
        company_name=args.company,
        campaign_id=args.campaign,
        applicant_id=args.applicant,
        trigger_reason=args.reason,
    ))


if __name__ == "__main__":
    main()

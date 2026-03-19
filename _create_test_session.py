"""Legt eine Test-Session direkt in der DB an ohne Template zu senden."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database import DatabaseClient
    await DatabaseClient.init_tables()

    # Alte Sessions cancellen
    pool = await DatabaseClient.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE whatsapp_sessions SET status='cancelled' WHERE to_number='4915204465582' AND status IN ('pending','active')"
        )

    # Neue Session anlegen
    session_id = await DatabaseClient.create_whatsapp_session(
        applicant_id="test_applicant_001",
        campaign_id="test_campaign_001",
        to_number="4915204465582",
        trigger_reason="voicemail",
        conversation_id="test_conv_001",
        candidate_first_name="David",
        candidate_last_name="Jekal",
        company_name="High Office sellcruiting",
        campaign_role_title="Pflegefachkraft",
    )
    print(f"Session {session_id} angelegt")

    # Template-Nachricht als ersten Bot-Eintrag speichern
    await DatabaseClient.append_whatsapp_message(
        session_id=session_id,
        role="agent",
        content="Hallo David, ich bin Laura, die digitale Bewerbungsassistenz von High Office sellcruiting. Wir haben versucht, Sie telefonisch zu erreichen. Sind Sie damit einverstanden, hier einen Chat zu starten?",
    )
    print(f"Bereit. Starte Test mit: python -X utf8 test_wa_webhook_sim.py --msg \"Ja, gerne\"")
    await DatabaseClient.close_pool()

asyncio.run(main())

"""
Skript zum Einreichen des Erstansprache-Templates bei Meta.

Verwendung:
    python create_wa_template.py

Voraussetzungen in .env:
    WHATSAPP_API_TOKEN=...
    WHATSAPP_WABA_ID=...
    WHATSAPP_API_VERSION=v22.0  (optional, default)

Das Template wird direkt an Meta submitted und muss dort genehmigt werden.
Status-Prüfung: python create_wa_template.py --status
"""
import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

# Src-Verzeichnis in Pfad aufnehmen
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dotenv import load_dotenv
load_dotenv()


# ─── Template-Definitionen ────────────────────────────────────────────────────

TEMPLATES = {
    "sellcruiting_fallback_de": {
        "description": "Erstansprache bei nicht erreichtem Bewerber (allgemein)",
        "body_text": (
            "Hallo {{1}}, ich bin Laura, die digitale Bewerbungsassistenz von {{2}}. "
            "Wir haben versucht, Sie telefonisch zu erreichen – leider ohne Erfolg. "
            "Möchten Sie Ihre Bewerbung in ca. 5 Minuten per Chat vervollständigen? "
            "Antworten Sie einfach mit \"Ja, gerne\"."
        ),
        "example_values": ["Max Mustermann", "Caritas GmbH"],
        "category": "UTILITY",
        "language": "de",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Ja, gerne"},
            {"type": "QUICK_REPLY", "text": "Nein danke"},
        ],
    },
    "sellcruiting_fallback_voicemail_de": {
        "description": "Erstansprache nach Mailbox-Erkennung",
        "body_text": (
            "Hallo {{1}}, hier ist Laura, die digitale Bewerbungsassistenz von {{2}}. "
            "Ich habe eben versucht, Sie anzurufen und bin auf Ihre Mailbox gestoßen. "
            "Damit Ihre Bewerbung nicht verloren geht: Möchten Sie die fehlenden "
            "Informationen kurz per Chat ergänzen? Das dauert ca. 5 Minuten."
        ),
        "example_values": ["Anna Beispiel", "Pflegezentrum Nord GmbH"],
        "category": "UTILITY",
        "language": "de",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Ja, gerne"},
            {"type": "QUICK_REPLY", "text": "Nein danke"},
        ],
    },
    "sellcruiting_fallback_busy_de": {
        "description": "Erstansprache wenn Leitung besetzt war (busy/no-answer)",
        "body_text": (
            "Hallo {{1}}, ich bin Laura, die digitale Bewerbungsassistenz von {{2}}. "
            "Wir haben gerade versucht, Sie zu erreichen – die Leitung war leider besetzt. "
            "Kein Problem! Möchten Sie Ihre Bewerbung kurz per Chat weiterführen? "
            "Das dauert nur ca. 5 Minuten."
        ),
        "example_values": ["Peter Muster", "Klinikum Stuttgart GmbH"],
        "category": "UTILITY",
        "language": "de",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Ja, gerne"},
            {"type": "QUICK_REPLY", "text": "Nein danke"},
        ],
    },
}


async def submit_template(template_key: str) -> None:
    """Reicht ein einzelnes Template bei Meta ein."""
    from whatsapp_cloud_client import WhatsAppCloudClient

    client = WhatsAppCloudClient()

    if not client.waba_id:
        print("❌ WHATSAPP_WABA_ID ist nicht gesetzt. Bitte in .env eintragen.")
        return

    if not client.api_token:
        print("❌ WHATSAPP_API_TOKEN ist nicht gesetzt. Bitte in .env eintragen.")
        return

    tpl = TEMPLATES.get(template_key)
    if not tpl:
        print(f"❌ Unbekanntes Template: {template_key}")
        print(f"   Verfügbare Templates: {list(TEMPLATES.keys())}")
        return

    print(f"\n📤 Sende Template '{template_key}' an Meta...")
    print(f"   Beschreibung: {tpl['description']}")
    print(f"   Kategorie: {tpl['category']} | Sprache: {tpl['language']}")
    print(f"   Text: {tpl['body_text'][:100]}...")

    result = await client.create_template(
        name=template_key,
        body_text=tpl["body_text"],
        example_values=tpl["example_values"],
        category=tpl["category"],
        language=tpl["language"],
        buttons=tpl.get("buttons"),
    )

    if result:
        print(f"\n✅ Template eingereicht!")
        print(f"   ID:     {result.get('id')}")
        print(f"   Status: {result.get('status')}")
        print(f"\n   ℹ️  Meta prüft das Template – dies dauert typischerweise")
        print(f"      wenige Minuten bis 24 Stunden.")
        print(f"   Status prüfen: python create_wa_template.py --status")
    else:
        print(f"\n❌ Template konnte nicht eingereicht werden.")
        print(f"   Prüfe WHATSAPP_API_TOKEN und WHATSAPP_WABA_ID in deiner .env")


async def submit_all_templates() -> None:
    """Reicht alle definierten Templates bei Meta ein."""
    for key in TEMPLATES:
        await submit_template(key)
        print()


async def check_status(template_name: str = None) -> None:
    """Prüft den Genehmigungsstatus aller oder eines bestimmten Templates."""
    from whatsapp_cloud_client import WhatsAppCloudClient

    client = WhatsAppCloudClient()

    if not client.waba_id:
        print("❌ WHATSAPP_WABA_ID ist nicht gesetzt.")
        return

    filter_info = f" (Filter: {template_name})" if template_name else " (alle)"
    print(f"\n🔍 Prüfe Template-Status{filter_info}...")

    templates = await client.get_template_status(template_name)

    if templates is None:
        print("❌ Fehler beim Abrufen des Status.")
        return

    if not templates:
        print("ℹ️  Keine Templates gefunden.")
        return

    print(f"\n{'Name':<45} {'Status':<15} {'Sprache':<10} {'Kategorie'}")
    print("-" * 90)

    for tpl in templates:
        status = tpl.get("status", "?")
        icon = "✅" if status == "APPROVED" else "⏳" if status == "PENDING" else "❌"
        print(
            f"{icon} {tpl.get('name', '?'):<43} "
            f"{status:<15} "
            f"{tpl.get('language', '?'):<10} "
            f"{tpl.get('category', '?')}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="WhatsApp Template Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python create_wa_template.py                          # Alle Templates einreichen
  python create_wa_template.py --template sellcruiting_fallback_de  # Einzelnes Template
  python create_wa_template.py --status                 # Status aller Templates
  python create_wa_template.py --status --template sellcruiting_fallback_de
  python create_wa_template.py --list                   # Verfügbare Templates anzeigen
        """,
    )
    parser.add_argument(
        "--template",
        help="Name des spezifischen Templates (ohne: alle)",
        default=None,
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Status der Templates bei Meta abfragen statt einreichen",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Verfügbare Templates anzeigen",
        dest="list_templates",
    )

    args = parser.parse_args()

    if args.list_templates:
        print("\n📋 Verfügbare Templates:\n")
        for key, tpl in TEMPLATES.items():
            print(f"  {key}")
            print(f"    {tpl['description']}")
            print(f"    Kategorie: {tpl['category']} | Sprache: {tpl['language']}")
            print(f"    Buttons: {[b['text'] for b in tpl.get('buttons', [])]}")
            print()
        return

    if args.status:
        asyncio.run(check_status(args.template))
        return

    if args.template:
        asyncio.run(submit_template(args.template))
    else:
        print("📦 Alle Templates werden eingereicht...\n")
        asyncio.run(submit_all_templates())


if __name__ == "__main__":
    main()

"""
Einfacher Test: Finde PLZ 14793 im Transkript mit Regex.
"""

import re

transcript_text = """
Agent: Jetzt brauche ich noch Ihre Postleitzahl, damit wir Sie richtig zuordnen können. Wie lautet Ihre Postleitzahl?
Kandidat: 14793
Agent: Danke. Das ist sieben eins vier sieben neun drei – habe ich das richtig?
Agent: Entschuldigung, können Sie mir die Postleitzahl nochmal wiederholen?
Kandidat: Das ist die 14793
Agent: Danke. Also eins vier sieben neun drei – stimmt das so?
Kandidat: Ja stimmt!
"""

print("=" * 70)
print("REGEX-TEST: PLZ-ERKENNUNG")
print("=" * 70)

print("\nText-Ausschnitt:")
print(transcript_text[:200] + "...")

# Simple regex
plz_matches = re.findall(r'\b(\d{5})\b', transcript_text)
print(f"\nGefundene 5-stellige Zahlen: {plz_matches}")

# Mit Kontext
lines = transcript_text.split('\n')
for i, line in enumerate(lines):
    if '14793' in line:
        print(f"\nZeile {i}: {line.strip()}")

print("\n" + "=" * 70)
if '14793' in plz_matches:
    print("SUCCESS: PLZ 14793 gefunden!")
else:
    print("FEHLER: PLZ nicht gefunden!")
print("=" * 70)

# Test ob LLM-Prompt das finden würde
prompt_keywords = ['postleitzahl', 'plz', 'wohne', 'wohnort']
found_keywords = [kw for kw in prompt_keywords if kw.lower() in transcript_text.lower()]
print(f"\nKontext-Keywords gefunden: {found_keywords}")
print(f"PLZ-Kontext vorhanden: {len(found_keywords) > 0}")

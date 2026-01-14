"""
Simple direct test of foreign qualification logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

# Just test the prompt is correctly updated
from extractor import Extractor

print("=" * 70)
print("PROMPT-CHECK: Auslaendische Ausbildung - Anerkennung")
print("=" * 70)

extractor = Extractor()
prompt = extractor._build_system_prompt()

# Check if recognition rules are in prompt
keywords = [
    "AUSLÄNDISCHE ABSCHLÜSSE",
    "deutsche Anerkennung",
    "checked: false",
    "Regierungspräsidium"
]

print("\nPRUEFE OB NEUE REGELN IM PROMPT SIND:\n")

for keyword in keywords:
    if keyword in prompt:
        print(f"  OK: '{keyword}' gefunden")
    else:
        print(f"  FEHLER: '{keyword}' NICHT gefunden!")

# Count how many times "AUSLÄNDISCHE" appears
count = prompt.count("AUSLÄNDISCHE")
print(f"\nAnzahl 'AUSLAENDISCHE' im Prompt: {count}")

if count > 0:
    print("\nSUCCESS! Die Anerkennungs-Regeln sind im Extractor-Prompt!")
else:
    print("\nFEHLER! Die Anerkennungs-Regeln fehlen!")

print("\n" + "=" * 70)

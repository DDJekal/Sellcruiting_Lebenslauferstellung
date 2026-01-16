"""Test Hybrid PLZ extraction (LLM + Regex Fallback)."""

# Simulate the logic from resume_builder.py
import re

# Simulate LLM result (no PLZ found)
llm_result = {
    'postal_code': None,  # LLM didn't find it!
    'city': None,
    'experiences': [],
    'educations': []
}

# Real transcript (simplified)
transcript = [
    {"speaker": "B", "text": "Jetzt brauche ich noch Ihre Postleitzahl, damit wir Sie richtig zuordnen können. Wie lautet Ihre Postleitzahl?"},
    {"speaker": "A", "text": "14793"},
    {"speaker": "B", "text": "Danke. Das ist sieben eins vier sieben neun drei – habe ich das richtig?"},
    {"speaker": "A", "text": "Das ist die 14793"},
    {"speaker": "B", "text": "Danke. Also eins vier sieben neun drei – stimmt das so?"},
    {"speaker": "A", "text": "Ja stimmt!"}
]

print("=" * 70)
print("HYBRID PLZ-EXTRAKTION TEST")
print("=" * 70)

postal_code_llm = llm_result.get('postal_code')

print(f"\n1. LLM Result: {postal_code_llm}")

# FALLBACK: If LLM didn't find PLZ, try regex as backup
if not postal_code_llm:
    print(f"\n2. LLM fand keine PLZ - versuche Regex-Fallback")
    full_text = ' '.join(turn.get('text', '') for turn in transcript)
    
    # Find all 5-digit numbers
    plz_matches = re.findall(r'\b(\d{5})\b', full_text)
    print(f"   Gefundene 5-stellige Zahlen: {plz_matches}")
    
    # Filter for PLZ context
    plz_keywords = ['postleitzahl', 'plz', 'wohne', 'wohnort', 'gezogen', 'umgezogen']
    
    # Try to find PLZ near context keywords
    for match in plz_matches:
        # Find context around this match
        match_pos = full_text.find(match)
        if match_pos > 0:
            context_before = full_text[max(0, match_pos-100):match_pos].lower()
            context_after = full_text[match_pos:min(len(full_text), match_pos+100)].lower()
            context = context_before + context_after
            
            # Check if any PLZ keyword is in context
            if any(keyword in context for keyword in plz_keywords):
                postal_code_llm = match
                print(f"   [FALLBACK] PLZ aus Regex extrahiert: {postal_code_llm}")
                print(f"   Kontext: ...{context[max(0, len(context)-50):]}...")
                break
    
    # If still not found, take first 5-digit number
    if not postal_code_llm and plz_matches:
        postal_code_llm = plz_matches[0]
        print(f"   [FALLBACK] PLZ aus erster 5-stelliger Zahl: {postal_code_llm}")

print("\n" + "=" * 70)
if postal_code_llm == "14793":
    print("SUCCESS! PLZ korrekt durch Hybrid-Ansatz extrahiert!")
else:
    print(f"FEHLER: PLZ = {postal_code_llm}")
print("=" * 70)

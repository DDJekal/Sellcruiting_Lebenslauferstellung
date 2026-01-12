"""Test: Vergleiche Output-Struktur von Claude vs GPT-4o."""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from llm_client import LLMClient


def test_output_structure():
    """Teste ob Claude und GPT-4o identische JSON-Strukturen liefern."""
    print("\n" + "="*70)
    print("TEST: OUTPUT-STRUKTUR CLAUDE VS GPT-4O")
    print("="*70)
    
    system_prompt = """Du bist ein Lebenslauf-Extractor.
Extrahiere aus dem Gespraech folgende Daten als JSON:

{
  "experiences": [
    {
      "position": string,
      "company": string,
      "start": "YYYY-MM-DD"|null,
      "end": "YYYY-MM-DD"|null,
      "tasks": string
    }
  ],
  "educations": [
    {
      "description": string,
      "company": string,
      "end": "YYYY-MM-DD"|null
    }
  ],
  "preferred_workload": string|null
}

Antworte NUR mit JSON, kein Text drumherum!
"""
    
    user_prompt = """Transkript:
A: Ich arbeite seit 2020 als Konstrukteur bei Siemens.
B: Welche Ausbildung haben Sie?
A: Bachelor Elektrotechnik an der TU Muenchen, abgeschlossen 2019.
B: Vollzeit oder Teilzeit?
A: Vollzeit, 40 Stunden.
"""
    
    print("\n1) TESTE MIT CLAUDE...")
    client_claude = LLMClient(prefer_claude=True)
    response_claude = client_claude.create_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0
    )
    
    print(f"\nClaude Response (Laenge: {len(response_claude)} Zeichen):")
    print(response_claude)
    
    try:
        data_claude = json.loads(response_claude)
        print("\n[OK] Claude: Valid JSON")
        print(f"Keys: {list(data_claude.keys())}")
        if 'experiences' in data_claude and len(data_claude['experiences']) > 0:
            print(f"Experience Keys: {list(data_claude['experiences'][0].keys())}")
        if 'educations' in data_claude and len(data_claude['educations']) > 0:
            print(f"Education Keys: {list(data_claude['educations'][0].keys())}")
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] Claude: Invalid JSON - {e}")
        return False
    
    print("\n" + "-"*70)
    print("\n2) TESTE MIT GPT-4O (Fallback)...")
    
    # Force GPT-4o by temporarily removing Claude access
    client_gpt = LLMClient(prefer_claude=False)
    response_gpt = client_gpt.create_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0
    )
    
    print(f"\nGPT-4o Response (Laenge: {len(response_gpt)} Zeichen):")
    print(response_gpt)
    
    try:
        data_gpt = json.loads(response_gpt)
        print("\n[OK] GPT-4o: Valid JSON")
        print(f"Keys: {list(data_gpt.keys())}")
        if 'experiences' in data_gpt and len(data_gpt['experiences']) > 0:
            print(f"Experience Keys: {list(data_gpt['experiences'][0].keys())}")
        if 'educations' in data_gpt and len(data_gpt['educations']) > 0:
            print(f"Education Keys: {list(data_gpt['educations'][0].keys())}")
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] GPT-4o: Invalid JSON - {e}")
        return False
    
    print("\n" + "="*70)
    print("3) STRUKTUR-VERGLEICH:")
    print("="*70)
    
    # Vergleiche Keys
    keys_match = set(data_claude.keys()) == set(data_gpt.keys())
    print(f"\nTop-Level Keys identisch: {keys_match}")
    print(f"  Claude: {sorted(data_claude.keys())}")
    print(f"  GPT-4o: {sorted(data_gpt.keys())}")
    
    # Vergleiche Experience-Struktur
    if 'experiences' in data_claude and 'experiences' in data_gpt:
        if len(data_claude['experiences']) > 0 and len(data_gpt['experiences']) > 0:
            exp_keys_match = set(data_claude['experiences'][0].keys()) == set(data_gpt['experiences'][0].keys())
            print(f"\nExperience Keys identisch: {exp_keys_match}")
            print(f"  Claude: {sorted(data_claude['experiences'][0].keys())}")
            print(f"  GPT-4o: {sorted(data_gpt['experiences'][0].keys())}")
    
    # Vergleiche Education-Struktur
    if 'educations' in data_claude and 'educations' in data_gpt:
        if len(data_claude['educations']) > 0 and len(data_gpt['educations']) > 0:
            edu_keys_match = set(data_claude['educations'][0].keys()) == set(data_gpt['educations'][0].keys())
            print(f"\nEducation Keys identisch: {edu_keys_match}")
            print(f"  Claude: {sorted(data_claude['educations'][0].keys())}")
            print(f"  GPT-4o: {sorted(data_gpt['educations'][0].keys())}")
    
    print("\n" + "="*70)
    
    # Finale Bewertung
    if keys_match:
        print("[SUCCESS] Output-Strukturen sind IDENTISCH!")
        print("="*70 + "\n")
        return True
    else:
        print("[WARNING] Output-Strukturen unterscheiden sich!")
        print("="*70 + "\n")
        return False


if __name__ == "__main__":
    success = test_output_structure()
    sys.exit(0 if success else 1)

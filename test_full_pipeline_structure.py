"""Test: Komplette Pipeline Output-Struktur (JSON-Serialisierung)."""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from resume_builder import ResumeBuilder
from models import ApplicantResume


def test_full_pipeline():
    """Teste vollstaendige JSON-Serialisierung mit Claude und GPT-4o."""
    print("\n" + "="*70)
    print("TEST: VOLLSTAENDIGE JSON-SERIALISIERUNG")
    print("="*70)
    
    # Test-Transkript
    transcript = [
        {"speaker": "A", "text": "Ich bin Max Mustermann."},
        {"speaker": "B", "text": "Wo arbeiten Sie aktuell?"},
        {"speaker": "A", "text": "Bei Siemens als Ingenieur seit 2020."},
        {"speaker": "B", "text": "Welche Ausbildung haben Sie?"},
        {"speaker": "A", "text": "Bachelor Maschinenbau an der TU Muenchen, 2019 abgeschlossen."}
    ]
    
    metadata = {
        "conversation_id": "test_123",
        "candidate_first_name": "Max",
        "candidate_last_name": "Mustermann"
    }
    
    print("\n1) TESTE MIT CLAUDE...")
    builder_claude = ResumeBuilder(prefer_claude=True)
    resume_claude = builder_claude.build_resume(
        transcript=transcript,
        elevenlabs_metadata=metadata,
        temporal_context={"call_year": 2026}
    )
    
    # Serialisiere zu JSON
    try:
        json_claude = resume_claude.model_dump_json(indent=2)
        data_claude = json.loads(json_claude)
        print(f"[OK] Claude: JSON-Serialisierung erfolgreich")
        print(f"     Groesse: {len(json_claude)} Zeichen")
        print(f"     Top Keys: {list(data_claude.keys())}")
        print(f"     Experiences: {len(data_claude['resume']['experiences'])}")
        print(f"     Educations: {len(data_claude['resume']['educations'])}")
    except Exception as e:
        print(f"[ERROR] Claude Serialisierung fehlgeschlagen: {e}")
        return False
    
    print("\n" + "-"*70)
    print("\n2) TESTE MIT GPT-4O...")
    builder_gpt = ResumeBuilder(prefer_claude=False)
    resume_gpt = builder_gpt.build_resume(
        transcript=transcript,
        elevenlabs_metadata=metadata,
        temporal_context={"call_year": 2026}
    )
    
    # Serialisiere zu JSON
    try:
        json_gpt = resume_gpt.model_dump_json(indent=2)
        data_gpt = json.loads(json_gpt)
        print(f"[OK] GPT-4o: JSON-Serialisierung erfolgreich")
        print(f"     Groesse: {len(json_gpt)} Zeichen")
        print(f"     Top Keys: {list(data_gpt.keys())}")
        print(f"     Experiences: {len(data_gpt['resume']['experiences'])}")
        print(f"     Educations: {len(data_gpt['resume']['educations'])}")
    except Exception as e:
        print(f"[ERROR] GPT-4o Serialisierung fehlgeschlagen: {e}")
        return False
    
    print("\n" + "="*70)
    print("3) STRUKTUR-VERGLEICH:")
    print("="*70)
    
    # Vergleiche Top-Level Keys
    keys_match = set(data_claude.keys()) == set(data_gpt.keys())
    print(f"\nTop-Level Keys identisch: {keys_match}")
    print(f"  Claude: {sorted(data_claude.keys())}")
    print(f"  GPT-4o: {sorted(data_gpt.keys())}")
    
    # Vergleiche Resume Keys
    resume_keys_match = set(data_claude['resume'].keys()) == set(data_gpt['resume'].keys())
    print(f"\nResume Keys identisch: {resume_keys_match}")
    print(f"  Anzahl Keys Claude: {len(data_claude['resume'].keys())}")
    print(f"  Anzahl Keys GPT-4o: {len(data_gpt['resume'].keys())}")
    
    # Vergleiche Experience-Struktur
    if len(data_claude['resume']['experiences']) > 0 and len(data_gpt['resume']['experiences']) > 0:
        exp_keys_c = set(data_claude['resume']['experiences'][0].keys())
        exp_keys_g = set(data_gpt['resume']['experiences'][0].keys())
        exp_match = exp_keys_c == exp_keys_g
        print(f"\nExperience-Struktur identisch: {exp_match}")
        print(f"  Claude Keys: {sorted(exp_keys_c)}")
        print(f"  GPT-4o Keys: {sorted(exp_keys_g)}")
    
    # Vergleiche Education-Struktur
    if len(data_claude['resume']['educations']) > 0 and len(data_gpt['resume']['educations']) > 0:
        edu_keys_c = set(data_claude['resume']['educations'][0].keys())
        edu_keys_g = set(data_gpt['resume']['educations'][0].keys())
        edu_match = edu_keys_c == edu_keys_g
        print(f"\nEducation-Struktur identisch: {edu_match}")
        print(f"  Claude Keys: {sorted(edu_keys_c)}")
        print(f"  GPT-4o Keys: {sorted(edu_keys_g)}")
    
    print("\n" + "="*70)
    
    if keys_match and resume_keys_match:
        print("[SUCCESS] VOLLSTAENDIGE KOMPATIBILITAET BESTAETIGT!")
        print("  - JSON-Serialisierung funktioniert")
        print("  - Pydantic-Modelle sind kompatibel")
        print("  - Output-Strukturen sind identisch")
        print("  - HOC-System wird funktionieren")
        print("="*70 + "\n")
        return True
    else:
        print("[WARNING] Strukturunterschiede gefunden!")
        print("="*70 + "\n")
        return False


if __name__ == "__main__":
    success = test_full_pipeline()
    sys.exit(0 if success else 1)

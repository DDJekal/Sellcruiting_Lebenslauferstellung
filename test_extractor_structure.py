"""Test: Extractor Output-Struktur mit Claude vs GPT-4o."""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from extractor import Extractor
from models import ShadowType, PromptType


def test_extractor_structure():
    """Teste ob Extractor mit Claude und GPT-4o identische Strukturen liefert."""
    print("\n" + "="*70)
    print("TEST: EXTRACTOR OUTPUT-STRUKTUR")
    print("="*70)
    
    # Test-Daten
    transcript = [
        {"speaker": "A", "text": "Ich habe eine Ausbildung als Pflegefachmann."},
        {"speaker": "B", "text": "Seit wann arbeiten Sie in der Pflege?"},
        {"speaker": "A", "text": "Seit 2020, also 6 Jahre."}
    ]
    
    shadow_types = {
        1: ShadowType(
            prompt_id=1,
            inferred_type=PromptType.YES_NO,
            confidence=0.95,
            reasoning="Qualifikationsfrage"
        ),
        2: ShadowType(
            prompt_id=2,
            inferred_type=PromptType.TEXT,
            confidence=0.90,
            reasoning="Erfahrungsfrage"
        )
    }
    
    prompts = [
        {"id": 1, "question": "Haben Sie eine Ausbildung als Pflegefachmann?"},
        {"id": 2, "question": "Wie viele Jahre Berufserfahrung haben Sie?"}
    ]
    
    grounding = {
        "campaign_id": 460,
        "questionnaire_name": "Pflege Test"
    }
    
    print("\n1) TESTE MIT CLAUDE...")
    extractor_claude = Extractor(prefer_claude=True)
    result_claude = extractor_claude.extract(
        transcript=transcript,
        shadow_types=shadow_types,
        grounding=grounding,
        prompts_to_fill=prompts
    )
    
    print(f"\n[OK] Claude: {len(result_claude)} Prompts gefuellt")
    for prompt_id, answer in result_claude.items():
        print(f"\n  Prompt {prompt_id}:")
        print(f"    checked: {answer.checked}")
        print(f"    value: {answer.value}")
        print(f"    confidence: {answer.confidence}")
        print(f"    evidence: {len(answer.evidence)} items")
        print(f"    notes: {answer.notes}")
    
    print("\n" + "-"*70)
    print("\n2) TESTE MIT GPT-4O...")
    extractor_gpt = Extractor(prefer_claude=False)
    result_gpt = extractor_gpt.extract(
        transcript=transcript,
        shadow_types=shadow_types,
        grounding=grounding,
        prompts_to_fill=prompts
    )
    
    print(f"\n[OK] GPT-4o: {len(result_gpt)} Prompts gefuellt")
    for prompt_id, answer in result_gpt.items():
        print(f"\n  Prompt {prompt_id}:")
        print(f"    checked: {answer.checked}")
        print(f"    value: {answer.value}")
        print(f"    confidence: {answer.confidence}")
        print(f"    evidence: {len(answer.evidence)} items")
        print(f"    notes: {answer.notes}")
    
    print("\n" + "="*70)
    print("3) STRUKTUR-VERGLEICH:")
    print("="*70)
    
    # Vergleiche ob gleiche Prompt-IDs gefuellt wurden
    ids_match = set(result_claude.keys()) == set(result_gpt.keys())
    print(f"\nGleiche Prompt-IDs gefuellt: {ids_match}")
    print(f"  Claude: {sorted(result_claude.keys())}")
    print(f"  GPT-4o: {sorted(result_gpt.keys())}")
    
    # Vergleiche Datentypen
    for prompt_id in result_claude.keys():
        if prompt_id in result_gpt:
            ans_c = result_claude[prompt_id]
            ans_g = result_gpt[prompt_id]
            
            print(f"\nPrompt {prompt_id}:")
            print(f"  checked type match: {type(ans_c.checked) == type(ans_g.checked)}")
            print(f"    Claude: {type(ans_c.checked).__name__}")
            print(f"    GPT-4o: {type(ans_g.checked).__name__}")
            
            print(f"  value type match: {type(ans_c.value) == type(ans_g.value)}")
            print(f"    Claude: {type(ans_c.value).__name__}")
            print(f"    GPT-4o: {type(ans_g.value).__name__}")
            
            print(f"  confidence type match: {type(ans_c.confidence) == type(ans_g.confidence)}")
            print(f"    Claude: {type(ans_c.confidence).__name__}")
            print(f"    GPT-4o: {type(ans_g.confidence).__name__}")
            
            print(f"  evidence type match: {type(ans_c.evidence) == type(ans_g.evidence)}")
            print(f"    Claude: {type(ans_c.evidence).__name__} with {len(ans_c.evidence)} items")
            print(f"    GPT-4o: {type(ans_g.evidence).__name__} with {len(ans_g.evidence)} items")
    
    print("\n" + "="*70)
    
    if ids_match:
        print("[SUCCESS] Extractor Output-Strukturen sind KOMPATIBEL!")
        print("="*70 + "\n")
        return True
    else:
        print("[WARNING] Extractor Output-Strukturen unterscheiden sich!")
        print("="*70 + "\n")
        return False


if __name__ == "__main__":
    success = test_extractor_structure()
    sys.exit(0 if success else 1)

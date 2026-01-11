"""Tests für Type Enricher Heuristiken (ohne API-Calls)."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.type_enricher import TypeEnricher
from src.models import MandantenConfig, PromptType


def test_type_enricher_heuristics():
    """Test Type Enricher Heuristiken für Auswahl- und Arbeitszeitfragen."""
    print("\n" + "=" * 70)
    print("TYPE ENRICHER HEURISTIK TESTS")
    print("=" * 70)
    
    # Mock enricher (ohne echten OpenAI client)
    enricher = TypeEnricher(api_key="dummy_key_for_testing")
    
    # Mock config
    config = MandantenConfig(
        mandant_id="test",
        protokoll_template_id=999,
        info_page_names=[]
    )
    
    # Test Cases
    test_cases = [
        {
            "id": 1,
            "question": "Station: Intensivstation, Geriatrie, Kardiologie, ZNA",
            "expected_type": PromptType.TEXT,
            "description": "Auswahlfrage mit 4 Optionen"
        },
        {
            "id": 2,
            "question": "Vollzeit: 38,5Std/Woche",
            "expected_type": PromptType.YES_NO_WITH_DETAILS,
            "description": "Arbeitszeitfrage mit Stundenzahl"
        },
        {
            "id": 3,
            "question": "Teilzeit: flexibel",
            "expected_type": PromptType.YES_NO,
            "description": "Arbeitszeitfrage ohne Stundenzahl"
        },
        {
            "id": 4,
            "question": "Schicht: Früh, Spät, Nacht, Wechselschicht",
            "expected_type": PromptType.TEXT,
            "description": "Schichtauswahl mit mehreren Optionen"
        },
        {
            "id": 5,
            "question": "Zwingend: Führerschein Klasse B",
            "expected_type": PromptType.YES_NO,
            "description": "Standard Zwingend-Frage"
        },
    ]
    
    print("\n[Heuristische Typenerkennung]")
    print("-" * 70)
    
    success_count = 0
    fail_count = 0
    
    for test_case in test_cases:
        prompt = {
            "id": test_case["id"],
            "question": test_case["question"]
        }
        
        # Rufe direkt die Heuristik auf (ohne LLM)
        shadow_type = enricher._apply_heuristics(prompt, "test_page", config)
        
        if shadow_type:
            detected_type = shadow_type.inferred_type
            confidence = shadow_type.confidence
            reasoning = shadow_type.reasoning
            
            # Vergleich
            is_correct = (detected_type == test_case["expected_type"])
            status = "[OK]" if is_correct else "[FEHLER]"
            
            if is_correct:
                success_count += 1
            else:
                fail_count += 1
            
            print(f"\n{status} Test #{test_case['id']}: {test_case['description']}")
            print(f"    Frage: {test_case['question']}")
            print(f"    Erwartet: {test_case['expected_type'].value}")
            print(f"    Erkannt:  {detected_type.value} (confidence: {confidence})")
            print(f"    Grund:    {reasoning}")
        else:
            fail_count += 1
            print(f"\n[FEHLER] Test #{test_case['id']}: {test_case['description']}")
            print(f"    Frage: {test_case['question']}")
            print(f"    Erwartet: {test_case['expected_type'].value}")
            print(f"    Erkannt:  KEINE HEURISTIK GEFUNDEN (würde an LLM weitergehen)")
    
    print("\n" + "=" * 70)
    print(f"ERGEBNIS: {success_count}/{len(test_cases)} Tests bestanden")
    print("=" * 70)
    
    if fail_count > 0:
        print(f"\n[WARNUNG] {fail_count} Tests fehlgeschlagen!")
        return False
    else:
        print("\n[SUCCESS] Alle Heuristiken funktionieren korrekt!")
        return True


def test_extractor_prompt_sections():
    """Test ob die neuen Prompt-Sections im Extractor vorhanden sind."""
    print("\n" + "=" * 70)
    print("EXTRACTOR PROMPT STRUCTURE TEST")
    print("=" * 70)
    
    from src.extractor import Extractor
    
    # Read extractor.py file
    extractor_path = os.path.join(os.path.dirname(__file__), "src", "extractor.py")
    with open(extractor_path, "r", encoding="utf-8") as f:
        extractor_code = f.read()
    
    # Check für wichtige Sections
    required_sections = [
        "REGELN FÜR ARBEITSZEITFRAGEN",
        "REGELN FÜR AUSWAHLFRAGEN",
        "Vollzeit: 38,5Std/Woche",
        "Station: Intensivstation, Geriatrie",
        "35 Stunden"
    ]
    
    print("\n[Prüfe Extractor System Prompt]")
    print("-" * 70)
    
    all_found = True
    for section in required_sections:
        if section in extractor_code:
            print(f"  [OK] Sektion gefunden: '{section[:50]}...'")
        else:
            print(f"  [FEHLER] Sektion fehlt: '{section}'")
            all_found = False
    
    print("\n" + "=" * 70)
    if all_found:
        print("[SUCCESS] Alle erforderlichen Prompt-Sections vorhanden!")
        return True
    else:
        print("[FEHLER] Einige Prompt-Sections fehlen!")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ROBUSTE ERKENNUNG - HEURISTIK TESTS")
    print("=" * 70)
    
    try:
        result1 = test_type_enricher_heuristics()
        result2 = test_extractor_prompt_sections()
        
        print("\n" + "=" * 70)
        if result1 and result2:
            print("ALLE TESTS BESTANDEN!")
            print("=" * 70)
            print("\nZusammenfassung:")
            print("  [OK] Type Enricher erkennt Auswahlfragen korrekt")
            print("  [OK] Type Enricher erkennt Arbeitszeitfragen korrekt")
            print("  [OK] Extractor-Prompt enthält alle erforderlichen Regeln")
            print("\n")
        else:
            print("EINIGE TESTS FEHLGESCHLAGEN!")
            print("=" * 70)
            exit(1)
        
    except Exception as e:
        print(f"\n[FEHLER] Unerwarteter Fehler: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)

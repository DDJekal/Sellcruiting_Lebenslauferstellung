"""Test script for new Qualification Groups functionality."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import json
import yaml

from models import (
    MandantenConfig, FilledProtocol, FilledPage, FilledPrompt, 
    PromptAnswer, Evidence, PromptType
)
from validator import Validator


def test_qualification_groups():
    """Test the new qualification groups evaluation."""
    
    print("=" * 80)
    print("TEST: Qualification Groups mit OR/AND-Logik")
    print("=" * 80)
    
    # 1. Load example config with qualification_groups
    config_path = Path("config/mandanten/template_460.yaml")
    
    if not config_path.exists():
        print("[X] Config nicht gefunden!")
        return
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    mandanten_config = MandantenConfig(**config_data)
    
    print(f"\n[OK] Config geladen: {mandanten_config.mandant_id}")
    print(f"   Anzahl Qualification Groups: {len(mandanten_config.qualification_groups)}")
    
    for group in mandanten_config.qualification_groups:
        print(f"\n   Gruppe: {group.group_name}")
        print(f"   - Logic: {group.logic}")
        print(f"   - Mandatory: {group.is_mandatory}")
        print(f"   - Options: {len(group.options)}")
        for opt in group.options:
            print(f"     * {opt.description} (Prompt {opt.prompt_id})")
    
    # 2. Create test filled protocol - SCENARIO 1: Qualified
    print("\n" + "=" * 80)
    print("SCENARIO 1: Bewerber mit Ausbildung als Pflegefachmann")
    print("=" * 80)
    
    filled_protocol_qualified = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    # Prompt 1001: Ausbildung Pflegefachmann (erfüllt!)
                    FilledPrompt(
                        id=1001,
                        question="Haben Sie eine Ausbildung als Pflegefachmann?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=True,
                            value="ja",
                            confidence=0.95,
                            evidence=[
                                Evidence(
                                    span="Ich habe eine Ausbildung als Pflegefachmann abgeschlossen",
                                    turn_index=5,
                                    speaker="A"
                                )
                            ],
                            notes="Explizit bestätigt"
                        )
                    ),
                    # Prompt 1002: Gesundheits- und Krankenpfleger (nicht erfüllt)
                    FilledPrompt(
                        id=1002,
                        question="Haben Sie eine Ausbildung als Gesundheits- und Krankenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=False,
                            value="nein",
                            confidence=0.9,
                            evidence=[],
                            notes="Nicht erwähnt"
                        )
                    ),
                    # Prompt 1003: Altenpfleger (nicht erfüllt)
                    FilledPrompt(
                        id=1003,
                        question="Haben Sie eine Ausbildung als Altenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Nicht erwähnt"
                        )
                    ),
                    # Prompt 3001: Deutschkenntnisse (implizit erfüllt)
                    FilledPrompt(
                        id=3001,
                        question="Haben Sie Deutschkenntnisse mindestens B2?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=True,
                            value="ja",
                            confidence=0.8,
                            evidence=[],
                            notes="Implizit angenommen (Gespräch auf Deutsch)"
                        )
                    )
                ]
            )
        ]
    )
    
    # Evaluate qualification
    validator = Validator()
    result = validator.evaluate_qualification(filled_protocol_qualified, mandanten_config)
    
    print(f"\n[!] ERGEBNIS:")
    print(f"   Qualifiziert: {'[JA]' if result['is_qualified'] else '[NEIN]'}")
    print(f"   Summary: {result['summary']}")
    print(f"   Methode: {result['evaluation_method']}")
    print(f"   Erfüllt: {result['fulfilled_count']}/{result['total_count']}")
    
    if result['errors']:
        print(f"\n   [X] Fehler:")
        for error in result['errors']:
            print(f"      - {error}")
    
    print(f"\n   [>] Gruppen-Details:")
    for group_eval in result['group_evaluations']:
        status = "[OK]" if group_eval['is_fulfilled'] else "[X]"
        print(f"   {status} {group_eval['group_name']} ({group_eval['logic']})")
        print(f"      Erfüllt: {group_eval['fulfilled_options']}/{group_eval['total_options']}")
        if group_eval['fulfilled_details']:
            for detail in group_eval['fulfilled_details']:
                print(f"      [+] {detail['description']} (Confidence: {detail['confidence']:.2f})")
    
    # 3. SCENARIO 2: Not qualified (keine Ausbildung)
    print("\n" + "=" * 80)
    print("SCENARIO 2: Bewerber OHNE Pflegeausbildung")
    print("=" * 80)
    
    filled_protocol_not_qualified = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    # Alle Ausbildungen nicht erfüllt
                    FilledPrompt(
                        id=1001,
                        question="Haben Sie eine Ausbildung als Pflegefachmann?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=False,
                            value="nein",
                            confidence=0.9,
                            evidence=[],
                            notes="Nicht erwähnt"
                        )
                    ),
                    FilledPrompt(
                        id=1002,
                        question="Haben Sie eine Ausbildung als Gesundheits- und Krankenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=False,
                            value="nein",
                            confidence=0.9,
                            evidence=[],
                            notes="Nicht erwähnt"
                        )
                    ),
                    FilledPrompt(
                        id=1003,
                        question="Haben Sie eine Ausbildung als Altenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=False,
                            value="nein",
                            confidence=0.9,
                            evidence=[],
                            notes="Nicht erwähnt"
                        )
                    ),
                    # Deutschkenntnisse erfüllt
                    FilledPrompt(
                        id=3001,
                        question="Haben Sie Deutschkenntnisse mindestens B2?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=True,
                            value="ja",
                            confidence=0.8,
                            evidence=[],
                            notes="Implizit angenommen"
                        )
                    )
                ]
            )
        ]
    )
    
    result2 = validator.evaluate_qualification(filled_protocol_not_qualified, mandanten_config)
    
    print(f"\n[!] ERGEBNIS:")
    print(f"   Qualifiziert: {'[JA]' if result2['is_qualified'] else '[NEIN]'}")
    print(f"   Summary: {result2['summary']}")
    print(f"   Erfüllt: {result2['fulfilled_count']}/{result2['total_count']}")
    
    if result2['errors']:
        print(f"\n   [X] Fehler:")
        for error in result2['errors']:
            print(f"      - {error}")
    
    print(f"\n   [>] Gruppen-Details:")
    for group_eval in result2['group_evaluations']:
        status = "[OK]" if group_eval['is_fulfilled'] else "[X]"
        print(f"   {status} {group_eval['group_name']} ({group_eval['logic']})")
        print(f"      Erfüllt: {group_eval['fulfilled_options']}/{group_eval['total_options']}")
    
    print("\n" + "=" * 80)
    print("[OK] TEST ABGESCHLOSSEN")
    print("=" * 80)


if __name__ == "__main__":
    test_qualification_groups()

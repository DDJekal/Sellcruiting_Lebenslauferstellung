"""
Integration Test: Realistische Kampagne mit Qualification Groups

Simuliert das Szenario:
- Kampagne 460: Pflegestelle mit mehreren Qualifikationsoptionen
- Bewerber Robin mit Ausbildung als Pflegefachmann
- System soll ihn als qualifiziert einstufen
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import yaml
from models import (
    MandantenConfig, FilledProtocol, FilledPage, FilledPrompt, 
    PromptAnswer, Evidence, PromptType
)
from validator import Validator


def test_real_scenario():
    """Test mit realistischem Szenario wie im User-Beispiel."""
    
    print("=" * 80)
    print("INTEGRATION TEST: Kampagne 460 - Robin als Pflegefachmann")
    print("=" * 80)
    
    # 1. Load config
    config_path = Path("config/mandanten/template_460.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    mandanten_config = MandantenConfig(**config_data)
    print(f"\n[1] Config geladen: {mandanten_config.mandant_id}")
    print(f"    Qualification Groups: {len(mandanten_config.qualification_groups)}")
    
    # 2. Simuliere gefülltes Protokoll wie es vom System kommt
    # Robin hat gesagt: "Ich habe eine Ausbildung als Pflegefachmann"
    
    filled_protocol = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    # Frage 1: Ausbildung Pflegefachmann
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
                                    span="Ich habe eine Ausbildung als Pflegefachmann",
                                    turn_index=8,
                                    speaker="A"
                                )
                            ],
                            notes="Explizit vom Bewerber bestätigt"
                        )
                    ),
                    # Frage 2: Andere Ausbildungen (nicht erwähnt)
                    FilledPrompt(
                        id=1002,
                        question="Haben Sie eine Ausbildung als Gesundheits- und Krankenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Nicht im Transkript erwähnt"
                        )
                    ),
                    FilledPrompt(
                        id=1003,
                        question="Haben Sie eine Ausbildung als Altenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Nicht im Transkript erwähnt"
                        )
                    ),
                    # Frage 3: Berufserfahrung (erwähnt: seit 2020 bei HEH-Kliniken)
                    FilledPrompt(
                        id=2001,
                        question="Haben Sie mindestens 1 Jahr Berufserfahrung?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=True,
                            value="seit 2020",
                            confidence=0.92,
                            evidence=[
                                Evidence(
                                    span="Ich arbeite seit Mai 2020 bei den HEH-Kliniken",
                                    turn_index=12,
                                    speaker="A"
                                )
                            ],
                            notes="5+ Jahre Erfahrung"
                        )
                    ),
                    # Frage 4: Deutschkenntnisse (implizit - Gespräch auf Deutsch)
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
    
    print("\n[2] Protokoll simuliert:")
    print("    - Ausbildung Pflegefachmann: JA (checked=True, confidence=0.95)")
    print("    - Berufserfahrung: JA (seit 2020)")
    print("    - Deutschkenntnisse: JA (implizit)")
    
    # 3. Evaluation durchführen
    validator = Validator()
    result = validator.evaluate_qualification(filled_protocol, mandanten_config)
    
    print("\n[3] EVALUATION ERGEBNIS:")
    print("=" * 80)
    
    if result['is_qualified']:
        print("    STATUS: [QUALIFIZIERT]")
    else:
        print("    STATUS: [NICHT QUALIFIZIERT]")
    
    print(f"\n    Summary: {result['summary']}")
    print(f"    Methode: {result['evaluation_method']}")
    print(f"    Erfuellt: {result['fulfilled_count']}/{result['total_count']}")
    
    if result['errors']:
        print(f"\n    Fehler:")
        for error in result['errors']:
            print(f"      [X] {error}")
    
    print(f"\n[4] GRUPPEN-DETAILS:")
    print("=" * 80)
    
    for group_eval in result['group_evaluations']:
        status = "[OK]" if group_eval['is_fulfilled'] else "[X]"
        mandatory = "(ZWINGEND)" if group_eval['is_mandatory'] else "(OPTIONAL)"
        
        print(f"\n    {status} {group_eval['group_name']} {mandatory}")
        print(f"        Logic: {group_eval['logic']}")
        print(f"        Erfuellt: {group_eval['fulfilled_options']}/{group_eval['total_options']}")
        
        if group_eval['fulfilled_details']:
            print(f"        Erfuellte Optionen:")
            for detail in group_eval['fulfilled_details']:
                print(f"          [+] {detail['description']}")
                print(f"              Confidence: {detail['confidence']:.2f}")
                print(f"              Value: {detail.get('value', 'N/A')}")
    
    print("\n" + "=" * 80)
    
    # 4. Vergleich mit erwarteter Ausgabe
    print("\n[5] VERGLEICH MIT ERWARTUNG:")
    print("=" * 80)
    
    expected_qualified = True
    actual_qualified = result['is_qualified']
    
    if expected_qualified == actual_qualified:
        print("    [OK] Erwartetes Ergebnis erreicht!")
        print(f"        Erwartet: qualifiziert={expected_qualified}")
        print(f"        Tatsaechlich: qualifiziert={actual_qualified}")
    else:
        print("    [FEHLER] Ergebnis weicht ab!")
        print(f"        Erwartet: qualifiziert={expected_qualified}")
        print(f"        Tatsaechlich: qualifiziert={actual_qualified}")
        return False
    
    # 5. Prüfe dass mindestens die Ausbildungs-Gruppe erfüllt ist
    ausbildung_group = next(
        (g for g in result['group_evaluations'] if 'Ausbildung' in g['group_name']),
        None
    )
    
    if ausbildung_group and ausbildung_group['is_fulfilled']:
        print("\n    [OK] Ausbildungs-Gruppe erfuellt!")
        print(f"        {ausbildung_group['fulfilled_options']} von {ausbildung_group['total_options']} Optionen erfuellt")
    else:
        print("\n    [FEHLER] Ausbildungs-Gruppe NICHT erfuellt!")
        return False
    
    print("\n" + "=" * 80)
    print("[SUCCESS] Integration Test bestanden!")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    success = test_real_scenario()
    exit(0 if success else 1)

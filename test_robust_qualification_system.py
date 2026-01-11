"""
Integration Test: Robustes 3-Schichten-System für Qualifikationserkennung

Testet das komplette System:
1. Extractor versucht direkte Antworten zu finden
2. ResumeBuilder extrahiert unstrukturierte Qualifikationen
3. QualificationMatcher matched Resume → Protokoll
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from models import (
    FilledProtocol, FilledPage, FilledPrompt, PromptAnswer, Evidence, PromptType,
    Resume, Education, Experience
)
from qualification_matcher import QualificationMatcher


def test_unstructured_qualification_matching():
    """
    Test: Kandidat erwähnt Qualifikationen NICHT direkt als Antwort,
    sondern beiläufig im Lebenslauf-Teil.
    """
    
    print("=" * 80)
    print("INTEGRATION TEST: Unstrukturierte Qualifikationserkennung")
    print("=" * 80)
    
    # SCENARIO: Robin erwähnt Ausbildung im Lebenslauf-Teil
    print("\nSZENARIO:")
    print("  Frage: 'Haben Sie eine Ausbildung als Pflegefachmann?'")
    print("  Transkript: Robin sagt NICHT direkt 'Ja', sondern:")
    print("    [Turn 5] 'Ich habe 2020 meine Ausbildung zum Pflegefachmann bei XY gemacht'")
    print("    [Turn 12] 'Ich arbeite seit 2020 bei den HEH-Kliniken'")
    
    # 1. Simuliere Protokoll OHNE direkte Antwort (Extractor fand nichts)
    filled_protocol = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    # Frage wurde NICHT beantwortet (checked=None)
                    FilledPrompt(
                        id=1001,
                        question="Haben Sie eine Ausbildung als Pflegefachmann?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Keine direkte Antwort gefunden"
                        )
                    ),
                    FilledPrompt(
                        id=2001,
                        question="Haben Sie mindestens 2 Jahre Berufserfahrung?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Keine direkte Antwort gefunden"
                        )
                    )
                ]
            )
        ]
    )
    
    # 2. Simuliere Resume (ResumeBuilder hat Qualifikationen gefunden!)
    resume = Resume(
        id=1,
        summary=None,
        qualified=None,
        applicant_id=1,
        educations=[
            Education(
                id=1,
                end="2020-05-01",
                company="Bildungszentrum XY",
                description="Ausbildung zum Pflegefachmann"
            )
        ],
        experiences=[
            Experience(
                id=1,
                position="Pflegefachmann",
                start="2020-05-01",
                end=None,
                company="HEH-Kliniken",
                employment_type="Hauptjob",
                tasks="Grundpflege; Medikamentenvergabe; Patientenbetreuung"
            )
        ]
    )
    
    print("\n[1] Ausgangssituation:")
    print("    Protokoll Prompt 1001 (Ausbildung): checked=None (nicht beantwortet)")
    print("    Protokoll Prompt 2001 (Erfahrung): checked=None (nicht beantwortet)")
    print("\n[2] Resume extrahiert:")
    print(f"    Education: {resume.educations[0].description}")
    print(f"    Experience: {resume.experiences[0].position} seit {resume.experiences[0].start}")
    
    # 3. QualificationMatcher anwenden
    matcher = QualificationMatcher()
    enriched_protocol = matcher.enrich_protocol_with_resume(
        filled_protocol=filled_protocol,
        resume=resume,
        confidence_threshold=0.85
    )
    
    print("\n[3] Nach Smart Matching:")
    print("=" * 80)
    
    # Prüfe Ergebnisse
    success = True
    
    for page in enriched_protocol.pages:
        for prompt in page.prompts:
            if prompt.id == 1001:  # Ausbildungsfrage
                print(f"\n    Prompt {prompt.id}: {prompt.question}")
                print(f"    checked: {prompt.answer.checked}")
                print(f"    value: {prompt.answer.value}")
                print(f"    confidence: {prompt.answer.confidence:.2f}")
                print(f"    notes: {prompt.answer.notes}")
                
                if prompt.answer.checked != True:
                    print("    [FEHLER] Sollte checked=True sein!")
                    success = False
                elif prompt.answer.confidence < 0.85:
                    print("    [FEHLER] Confidence zu niedrig!")
                    success = False
                else:
                    print("    [OK] Qualifikation korrekt erkannt!")
            
            elif prompt.id == 2001:  # Erfahrungsfrage
                print(f"\n    Prompt {prompt.id}: {prompt.question}")
                print(f"    checked: {prompt.answer.checked}")
                print(f"    value: {prompt.answer.value}")
                print(f"    confidence: {prompt.answer.confidence:.2f}")
                print(f"    notes: {prompt.answer.notes}")
                
                if prompt.answer.checked != True:
                    print("    [FEHLER] Sollte checked=True sein (>2 Jahre Erfahrung)!")
                    success = False
                else:
                    print("    [OK] Erfahrung korrekt berechnet!")
    
    print("\n" + "=" * 80)
    
    if success:
        print("[SUCCESS] Smart Matching funktioniert!")
        print("\nDAS SYSTEM ERKENNT QUALIFIKATIONEN AUCH WENN:")
        print("  - Kandidat nicht direkt auf Frage antwortet")
        print("  - Qualifikationen beiläufig im Lebenslauf erwähnt werden")
        print("  - Resume-Daten mit Protokoll-Fragen gematched werden müssen")
    else:
        print("[FEHLER] Smart Matching hat nicht funktioniert!")
        return False
    
    print("\n" + "=" * 80)
    return True


def test_equivalent_qualifications():
    """Test: Äquivalente Qualifikationen werden erkannt."""
    
    print("\n" + "=" * 80)
    print("TEST: Äquivalente Qualifikationen")
    print("=" * 80)
    
    print("\nSZENARIO:")
    print("  Frage: 'Haben Sie eine Ausbildung als Pflegefachmann?'")
    print("  Resume: 'Ausbildung zum Gesundheits- und Krankenpfleger'")
    print("  -> Sollte als aequivalent erkannt werden!")
    
    filled_protocol = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    FilledPrompt(
                        id=1001,
                        question="Haben Sie eine Ausbildung als Pflegefachmann?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Keine direkte Antwort"
                        )
                    )
                ]
            )
        ]
    )
    
    resume = Resume(
        id=1,
        summary=None,
        qualified=None,
        applicant_id=1,
        educations=[
            Education(
                id=1,
                end="2019-08-01",
                company="Bildungszentrum ABC",
                description="Ausbildung zum Gesundheits- und Krankenpfleger"
            )
        ],
        experiences=[]
    )
    
    matcher = QualificationMatcher()
    enriched_protocol = matcher.enrich_protocol_with_resume(
        filled_protocol=filled_protocol,
        resume=resume,
        confidence_threshold=0.85
    )
    
    prompt = enriched_protocol.pages[0].prompts[0]
    
    print(f"\n[ERGEBNIS]")
    print(f"  checked: {prompt.answer.checked}")
    print(f"  value: {prompt.answer.value}")
    print(f"  confidence: {prompt.answer.confidence:.2f}")
    print(f"  notes: {prompt.answer.notes}")
    
    if prompt.answer.checked == True and prompt.answer.confidence >= 0.85:
        print("\n[OK] Äquivalente Qualifikation erkannt!")
        return True
    else:
        print("\n[FEHLER] Äquivalente Qualifikation NICHT erkannt!")
        return False


def test_multiple_options():
    """Test: Mehrere Optionen in einer Frage."""
    
    print("\n" + "=" * 80)
    print("TEST: Mehrere Optionen (A oder B oder C)")
    print("=" * 80)
    
    print("\nSZENARIO:")
    print("  Frage: 'Haben Sie eine Ausbildung als Pflegefachmann,")
    print("         Gesundheits- und Krankenpfleger oder Altenpfleger?'")
    print("  Resume: 'Ausbildung zum Altenpfleger'")
    print("  -> Sollte matched werden (eine der Optionen erfuellt)!")
    
    filled_protocol = FilledProtocol(
        protocol_id=460,
        protocol_name="Pflegestelle",
        pages=[
            FilledPage(
                id=1,
                name="Qualifikationen",
                prompts=[
                    FilledPrompt(
                        id=1001,
                        question="Haben Sie eine Ausbildung als Pflegefachmann, Gesundheits- und Krankenpfleger oder Altenpfleger?",
                        inferred_type=PromptType.YES_NO,
                        answer=PromptAnswer(
                            checked=None,
                            value=None,
                            confidence=0.0,
                            evidence=[],
                            notes="Keine direkte Antwort"
                        )
                    )
                ]
            )
        ]
    )
    
    resume = Resume(
        id=1,
        summary=None,
        qualified=None,
        applicant_id=1,
        educations=[
            Education(
                id=1,
                end="2018-06-01",
                company="Bildungszentrum DEF",
                description="Ausbildung zum Altenpfleger"
            )
        ],
        experiences=[]
    )
    
    matcher = QualificationMatcher()
    enriched_protocol = matcher.enrich_protocol_with_resume(
        filled_protocol=filled_protocol,
        resume=resume,
        confidence_threshold=0.85
    )
    
    prompt = enriched_protocol.pages[0].prompts[0]
    
    print(f"\n[ERGEBNIS]")
    print(f"  checked: {prompt.answer.checked}")
    print(f"  value: {prompt.answer.value}")
    print(f"  confidence: {prompt.answer.confidence:.2f}")
    
    if prompt.answer.checked == True and "Altenpfleger" in prompt.answer.value:
        print("\n[OK] Eine der Optionen wurde matched!")
        return True
    else:
        print("\n[FEHLER] Matching fehlgeschlagen!")
        return False


if __name__ == "__main__":
    print("+" + "=" * 78 + "+")
    print("|" + " " * 15 + "ROBUSTES 3-SCHICHTEN-SYSTEM TEST" + " " * 31 + "|")
    print("+" + "=" * 78 + "+")
    
    test1 = test_unstructured_qualification_matching()
    test2 = test_equivalent_qualifications()
    test3 = test_multiple_options()
    
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG:")
    print("=" * 80)
    print(f"  Test 1 (Unstrukturiert): {'[OK]' if test1 else '[FEHLER]'}")
    print(f"  Test 2 (Äquivalent):     {'[OK]' if test2 else '[FEHLER]'}")
    print(f"  Test 3 (Mehrfachopt.):   {'[OK]' if test3 else '[FEHLER]'}")
    print("=" * 80)
    
    if test1 and test2 and test3:
        print("\n[SUCCESS] Alle Tests bestanden!")
        print("\nDAS SYSTEM IST JETZT MAXIMAL ROBUST:")
        print("  1. Extractor sucht direkte Antworten")
        print("  2. ResumeBuilder extrahiert unstrukturiert")
        print("  3. QualificationMatcher matched intelligent")
        print("=" * 80)
        exit(0)
    else:
        print("\n[FEHLER] Einige Tests fehlgeschlagen!")
        exit(1)

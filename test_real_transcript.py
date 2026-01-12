"""Test mit echtem Anrufprotokoll - Flughafen Nürnberg."""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from extractor import Extractor
from type_enricher import TypeEnricher
from models import ShadowType, PromptType


def test_real_transcript():
    """Teste mit echtem Anrufprotokoll."""
    print("\n" + "="*70)
    print("TEST: ECHTES ANRUFPROTOKOLL - FLUGHAFEN NUERNBERG")
    print("="*70)
    
    # Echtes Transkript (vereinfacht für Test)
    transcript = [
        {"speaker": "A", "text": "Also er ist jetzt ganz neu in Deutschland und er moechte auf jeden Fall hier sich integrieren und die Sprache auch richtig gut beherrschen."},
        {"speaker": "B", "text": "Wie wuerden Sie Ihre Deutschkenntnisse aktuell selbst einschaetzen?"},
        {"speaker": "A", "text": "Also im A1-Modus in der Tuerkei hat er mit A1 angefangen und er hat fast absolviert gehabt. Hier macht er jetzt nur noch den Test."},
        {"speaker": "B", "text": "Welchen Fuehrerschein hat er?"},
        {"speaker": "A", "text": "Er hat Klasse B, der ist aber in der Tuerkei meist gueltig und sechs Monate nur in Deutschland. Aber er hat jetzt gerade auch vor, das Ganze umzumelden."},
        {"speaker": "B", "text": "Wie sieht es mit der Bereitschaft zur Wechselschicht-Tauglichkeit aus?"},
        {"speaker": "A", "text": "Das ist fuer meinen Mann gar kein Problem, weil er schon das Schichtsystem allgemein kennt und auch darin sehr, sehr lange gearbeitet hat."},
        {"speaker": "B", "text": "Wie steht es mit der koerperlichen Belastbarkeit?"},
        {"speaker": "A", "text": "Das ist fuer ihn auch gar kein Problem, da er auch Fitnesscoach zugleich war und er trainiert auch diesbezueglich."},
        {"speaker": "B", "text": "Koennen Sie mir etwas zu seiner Ausbildung oder seinem Schulabschluss erzaehlen?"},
        {"speaker": "A", "text": "Also eine Ausbildung hat er schon gestartet gehabt, ganz wo er jung war, aber das hat er nicht vollendet, das war im Kfz-Bereich."},
        {"speaker": "A", "text": "Er wollte weiter in die Schule und deswegen hatte nach ein paar Jahren seinen Gymnasiumabschluss jetzt ganz frisch nochmal gemacht."},
        {"speaker": "A", "text": "Aber als Qualifikation und Zertifikat hat er sich quasi zum Immobilienmakler weiterentwickelt und hat dann den Test bestanden."},
        {"speaker": "B", "text": "Koennen Sie mir die wichtigsten drei Positionen nennen?"},
        {"speaker": "A", "text": "Also er hat in der Produktion fuenf Jahre lang gearbeitet. Das war einfach die Stelle, wo er am laengsten gearbeitet hatte."},
        {"speaker": "A", "text": "Und das war quasi fuer Autoteile bestimmt, dass die Produktion ueber halt Autoteile, Lenkrad und Sitze und Sonstiges dort produziert wurde."},
        {"speaker": "A", "text": "Als Immobilienmakler hat er sich qualifiziert gehabt und da hat er auch darin eineinhalb bis zwei Jahre gearbeitet."},
        {"speaker": "A", "text": "Und zuletzt hat er dann auch als sozusagen Teamleiter oder Steuerer, Koordinierer in einem Buero, in einem Tourismusbuero gearbeitet."},
        {"speaker": "B", "text": "Bei der Produktion - wann hat er dort angefangen und wann beendet?"},
        {"speaker": "A", "text": "Also 2018 bis 2023 hat er bei der Produktion fuer Autoteile gearbeitet."},
        {"speaker": "A", "text": "Und beim Immobilienmakler hat er 2024 angefangen, bis Juli 2025 hat er dort gearbeitet."},
        {"speaker": "A", "text": "Ab Juli hat er dann quasi bei dieser Tourismusfirma angefangen."},
        {"speaker": "B", "text": "Wann koennte er fruehestens bei uns starten?"},
        {"speaker": "A", "text": "Ab sofort."}
    ]
    
    # Test-Prompts (typisch für Flughafen-Job)
    prompts = [
        {"id": 1, "question": "Haben Sie einen Fuehrerschein Klasse B?"},
        {"id": 2, "question": "Sind Sie bereit fuer Wechselschicht (24/7)?"},
        {"id": 3, "question": "Sind Sie koerperlich belastbar?"},
        {"id": 4, "question": "Welchen Schulabschluss haben Sie?"},
        {"id": 5, "question": "Haben Sie eine Berufsausbildung?"},
        {"id": 6, "question": "Wie viele Jahre Berufserfahrung haben Sie?"},
        {"id": 7, "question": "Deutschkenntnisse (mindestens A2)?"}
    ]
    
    print("\n1) TYPE ENRICHER (mit Claude)...")
    enricher = TypeEnricher(prefer_claude=True)
    shadow_types = {}
    for prompt in prompts:
        shadow_types[prompt["id"]] = ShadowType(
            prompt_id=prompt["id"],
            inferred_type=PromptType.YES_NO,
            confidence=0.9,
            reasoning="Test"
        )
    
    print(f"   Types inferred: {len(shadow_types)}")
    
    print("\n2) EXTRACTOR (mit Claude + neuen Regeln)...")
    extractor = Extractor(prefer_claude=True)
    
    grounding = {
        "campaign_id": 999,
        "questionnaire_name": "Flughafen Test"
    }
    
    answers = extractor.extract(
        transcript=transcript,
        shadow_types=shadow_types,
        grounding=grounding,
        prompts_to_fill=prompts
    )
    
    print(f"   Answers extracted: {len(answers)}")
    
    print("\n" + "="*70)
    print("ERGEBNISSE:")
    print("="*70)
    
    for prompt in prompts:
        prompt_id = prompt["id"]
        if prompt_id in answers:
            answer = answers[prompt_id]
            print(f"\n[{prompt_id}] {prompt['question']}")
            print(f"    checked: {answer.checked}")
            print(f"    value: {answer.value}")
            print(f"    confidence: {answer.confidence:.2f}")
            print(f"    evidence: {len(answer.evidence)} items")
            if answer.evidence:
                for ev in answer.evidence[:2]:  # Erste 2 Evidence
                    print(f"      - Turn {ev.turn_index}: '{ev.span[:50]}...'")
            if answer.notes:
                print(f"    notes: {answer.notes[:80]}...")
    
    print("\n" + "="*70)
    print("QUALITAETS-CHECKS:")
    print("="*70)
    
    # Check 1: Multi-Turn Reasoning
    print("\n1. MULTI-TURN REASONING:")
    schulabschluss_answer = answers.get(4)
    if schulabschluss_answer and len(schulabschluss_answer.evidence) > 1:
        print("   [OK] Schulabschluss hat mehrere Evidence-Eintrage!")
        print(f"       {len(schulabschluss_answer.evidence)} Turns kombiniert")
    else:
        print("   [WARN] Schulabschluss hat nur 1 Evidence")
    
    # Check 2: Synonym-Erkennung
    print("\n2. SYNONYM-ERKENNUNG:")
    ausbildung_answer = answers.get(5)
    if ausbildung_answer:
        if ausbildung_answer.checked == False:
            print("   [OK] Keine formale Ausbildung erkannt (Kfz nicht vollendet)")
        elif ausbildung_answer.checked == True:
            print(f"   [INFO] Als qualifiziert erkannt: {ausbildung_answer.value}")
            print(f"   [INFO] Confidence: {ausbildung_answer.confidence:.2f}")
    
    # Check 3: Negative Patterns
    print("\n3. NEGATIVE PATTERNS:")
    if ausbildung_answer and ausbildung_answer.checked == False:
        print("   [OK] Negative erkannt: 'hat nicht vollendet'")
        if "aber" in ausbildung_answer.notes.lower():
            print("   [OK] 'aber' Kompensation geprueft")
    
    # Check 4: Confidence-Kalibrierung
    print("\n4. CONFIDENCE-SCORES:")
    for prompt in prompts:
        if prompt["id"] in answers:
            ans = answers[prompt["id"]]
            if ans.checked is not None:
                if ans.confidence >= 0.85:
                    level = "HOCH"
                elif ans.confidence >= 0.75:
                    level = "MITTEL-HOCH"
                elif ans.confidence >= 0.65:
                    level = "MITTEL"
                else:
                    level = "NIEDRIG"
                print(f"   [{prompt['id']}] {ans.confidence:.2f} ({level})")
    
    print("\n" + "="*70)
    print("TEST ABGESCHLOSSEN")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_real_transcript()

"""
Test German recognition logic in Extractor.
Tests if candidates with foreign qualifications are correctly qualified/disqualified.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

import json
from extractor import Extractor
from mapper import Mapper
from config_parser import ConfigParser

print("=" * 70)
print("TEST: AUSLAENDISCHE AUSBILDUNG - QUALIFIZIERUNGS-LOGIK")
print("=" * 70)

# Load real config
config_path = "config/mandanten/template_460.yaml"
config_parser = ConfigParser()
mandanten_config = config_parser.parse_config(config_path)

# Create simple protocol
from models import FilledProtocol, FilledPage, FilledPrompt, PromptType, PromptAnswer

simple_protocol = FilledProtocol(
    protocol_id=460,
    protocol_name="Pflege Test",
    pages=[
        FilledPage(
            page_id=1,
            page_name="Qualifikation",
            prompts=[
                FilledPrompt(
                    id=1001,
                    question="Haben Sie eine Ausbildung als Pflegefachmann?",
                    type=PromptType.YES_NO,
                    inferred_type=None,
                    answer=PromptAnswer()
                )
            ]
        )
    ]
)

# Test cases
test_cases = [
    {
        "name": "Fall 1: Auslaendisch MIT Anerkennung",
        "transcript": [
            {"speaker": "Agent", "text": "Haben Sie eine Ausbildung als Pflegefachmann?"},
            {"speaker": "Applicant", "text": "Ja, in der Tuerkei gemacht und 2023 vom Regierungspraesidium Stuttgart in Deutschland anerkannt."}
        ],
        "expected_checked": True,
        "expected_confidence_min": 0.90
    },
    {
        "name": "Fall 2: Auslaendisch OHNE Anerkennung",
        "transcript": [
            {"speaker": "Agent", "text": "Haben Sie eine Ausbildung als Pflegefachmann?"},
            {"speaker": "Applicant", "text": "Ja, in der Tuerkei habe ich das gelernt."}
        ],
        "expected_checked": False,
        "expected_confidence_min": 0.85
    },
    {
        "name": "Fall 3: Anerkennung beantragt (noch nicht da)",
        "transcript": [
            {"speaker": "Agent", "text": "Haben Sie eine Ausbildung als Pflegefachmann?"},
            {"speaker": "Applicant", "text": "Ja, aus Syrien. Die Anerkennung habe ich beantragt, laeuft noch."}
        ],
        "expected_checked": False,
        "expected_confidence_min": 0.80
    },
    {
        "name": "Fall 4: Deutsche Ausbildung (keine Anerkennung noetig)",
        "transcript": [
            {"speaker": "Agent", "text": "Haben Sie eine Ausbildung als Pflegefachmann?"},
            {"speaker": "Applicant", "text": "Ja, in Deutschland gemacht, in Nuernberg."}
        ],
        "expected_checked": True,
        "expected_confidence_min": 0.90
    }
]

extractor = Extractor()

print("\n")
for i, test_case in enumerate(test_cases, 1):
    print(f"\n{'=' * 70}")
    print(f"TEST {i}: {test_case['name']}")
    print("=" * 70)
    
    print("\nTranskript:")
    for turn in test_case['transcript']:
        print(f"  {turn['speaker']}: {turn['text']}")
    
    # Run extraction
    result = extractor.fill_protocol(simple_protocol, test_case['transcript'])
    
    # Get the answer
    answer = result.pages[0].prompts[0].answer
    
    print(f"\nERGEBNIS:")
    print(f"  checked: {answer.checked}")
    print(f"  value: {answer.value}")
    print(f"  confidence: {answer.confidence:.2f}")
    print(f"  notes: {answer.notes[:80] if answer.notes else 'None'}...")
    
    # Validate
    print(f"\nVALIDIERUNG:")
    
    # Check checked value
    if answer.checked == test_case['expected_checked']:
        print(f"  OK checked: {answer.checked} (erwartet: {test_case['expected_checked']})")
    else:
        print(f"  FEHLER checked: {answer.checked} (erwartet: {test_case['expected_checked']})")
    
    # Check confidence
    if answer.confidence >= test_case['expected_confidence_min']:
        print(f"  OK confidence: {answer.confidence:.2f} (min: {test_case['expected_confidence_min']})")
    else:
        print(f"  FEHLER confidence: {answer.confidence:.2f} (min: {test_case['expected_confidence_min']})")
    
    # Overall result
    passed = (
        answer.checked == test_case['expected_checked'] and
        answer.confidence >= test_case['expected_confidence_min']
    )
    
    if passed:
        print(f"\n  >>> TEST BESTANDEN <<<")
    else:
        print(f"\n  >>> TEST FEHLGESCHLAGEN <<<")

print("\n" + "=" * 70)
print("ALLE TESTS ABGESCHLOSSEN")
print("=" * 70)

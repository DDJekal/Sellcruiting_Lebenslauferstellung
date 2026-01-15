"""
Test short conversation WITHOUT implicit defaults.
Verifies that short conversations are correctly marked as NOT qualified.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

import json
from models import FilledProtocol, FilledPage, FilledPrompt, PromptType, PromptAnswer, MandantenConfig
from validator import Validator
import yaml

print("=" * 70)
print("TEST: KURZES GESPRAECH OHNE IMPLICIT DEFAULTS")
print("=" * 70)

# Load config
with open("config/mandanten/kita_urban.yaml", 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)
mandanten_config = MandantenConfig(**config_data)

print(f"\nConfig: {mandanten_config.mandant_id}")
print(f"Implicit Defaults: {len(mandanten_config.implicit_defaults)}")

# Create short conversation protocol (12 seconds, hung up)
short_protocol = FilledProtocol(
    protocol_id=62,
    protocol_name="Kita Urban - Kurzes Gespraech",
    pages=[
        FilledPage(
            page_id=1,
            page_name="Qualifikation",
            prompts=[
                FilledPrompt(
                    id=281,
                    question="Zwingend: Staatlich anerkannter sozialpädagogischer Abschluss...",
                    type=PromptType.YES_NO,
                    inferred_type=PromptType.YES_NO,  # Set to YES_NO
                    answer=PromptAnswer(
                        checked=None,  # Not answered (hung up)
                        confidence=0.0,
                        evidence=[]
                    )
                ),
                FilledPrompt(
                    id=289,
                    question="Zwingend: Deutschkenntnisse B2...",
                    type=PromptType.YES_NO,
                    inferred_type=PromptType.YES_NO,  # Set to YES_NO
                    answer=PromptAnswer(
                        checked=None,  # Not answered (hung up)
                        confidence=0.0,
                        evidence=[]
                    )
                )
            ]
        )
    ]
)

print("\n" + "=" * 70)
print("PROTOKOLL (vor implicit defaults):")
print("=" * 70)

for prompt in short_protocol.pages[0].prompts:
    print(f"\nPrompt {prompt.id}: {prompt.question[:50]}...")
    print(f"  checked: {prompt.answer.checked}")
    print(f"  confidence: {prompt.answer.confidence}")
    print(f"  evidence: {len(prompt.answer.evidence)} items")

# Apply implicit defaults (should do NOTHING now!)
validator = Validator()
filled_protocol = validator.apply_implicit_defaults(short_protocol, mandanten_config)

print("\n" + "=" * 70)
print("PROTOKOLL (nach implicit defaults - sollte GLEICH sein!):")
print("=" * 70)

for prompt in filled_protocol.pages[0].prompts:
    print(f"\nPrompt {prompt.id}: {prompt.question[:50]}...")
    print(f"  checked: {prompt.answer.checked}")
    print(f"  confidence: {prompt.answer.confidence}")
    print(f"  evidence: {len(prompt.answer.evidence)} items")

# Evaluate qualification
qualification = validator.evaluate_qualification(filled_protocol, mandanten_config)

print("\n" + "=" * 70)
print("QUALIFIZIERUNGS-ERGEBNIS:")
print("=" * 70)

print(f"\nQualified: {qualification['is_qualified']}")
print(f"Summary: {qualification['summary']}")
print(f"Method: {qualification['evaluation_method']}")
print(f"Fulfilled: {qualification['fulfilled_count']}/{qualification['total_count']}")
print(f"\nErrors:")
for error in qualification['errors']:
    print(f"  - {error}")

print("\n" + "=" * 70)
if not qualification['is_qualified']:
    print("SUCCESS! Kurzes Gespraech korrekt als NICHT qualifiziert erkannt!")
else:
    print("FEHLER! Kurzes Gespraech faelschlicherweise als qualifiziert erkannt!")
print("=" * 70)

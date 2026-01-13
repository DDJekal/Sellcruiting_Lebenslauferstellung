"""
Test PLZ extraction from real transcript.
"""

import sys
import os

# Add src to path for local testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import json
from resume_builder import ResumeBuilder
from temporal_enricher import TemporalEnricher

# Test transcript with PLZ
test_transcript = [
    {"speaker": "Agent", "text": "Guten Tag! Hier ist Lisa vom Flughafen Nuernberg."},
    {"speaker": "Applicant", "text": "Hallo, ich bin 35 Jahre alt."},
    {"speaker": "Agent", "text": "Wo wohnen Sie denn?"},
    {"speaker": "Applicant", "text": "Ich wohne ganz in der Naehe, in 90402 Nuernberg."},
    {"speaker": "Agent", "text": "Prima! Haben Sie einen Fuehrerschein?"},
    {"speaker": "Applicant", "text": "Ja, Klasse B habe ich."},
]

# Test with ElevenLabs metadata
test_metadata = {
    "conversation_id": "test_plz_123",
    "candidate_first_name": "Max",
    "candidate_last_name": "Mustermann",
    "to_number": "+49 911 12345678"
}

print("=" * 70)
print("TEST: PLZ-EXTRAKTION AUS TRANSKRIPT")
print("=" * 70)

print("\n1) Transkript:")
for turn in test_transcript:
    print(f"   {turn['speaker']}: {turn['text'][:60]}...")

print("\n2) TEMPORAL ENRICHER...")
enricher = TemporalEnricher()
enriched_transcript = enricher.enrich_transcript(test_transcript, use_mcp=False)
temporal_context = enricher.extract_temporal_context(enriched_transcript)
print(f"   Temporal context: {temporal_context}")

print("\n3) RESUME BUILDER (mit LLM-PLZ-Extraktion)...")
builder = ResumeBuilder()
result = builder.build_resume(
    transcript=enriched_transcript,
    elevenlabs_metadata=test_metadata,
    temporal_context=temporal_context
)

print("\n" + "=" * 70)
print("ERGEBNIS:")
print("=" * 70)

print("\n[APPLICANT]")
print(f"  ID: {result.applicant.id}")
print(f"  Name: {result.applicant.first_name} {result.applicant.last_name}")
print(f"  Phone: {result.applicant.phone}")
print(f"  PLZ: {result.applicant.postal_code}")

print("\n[RESUME]")
print(f"  ID: {result.resume.id}")
print(f"  PLZ (aus LLM): {result.resume.postal_code}")
print(f"  Stadt (aus LLM): {result.resume.city}")

print("\n" + "=" * 70)
if result.applicant.postal_code == "90402":
    print("ERFOLG! PLZ korrekt extrahiert (90402 Nuernberg)")
else:
    print(f"FEHLER! Erwartete '90402', bekam '{result.applicant.postal_code}'")
print("=" * 70)

# Save result for inspection
with open("Output/test_plz_result.json", "w", encoding="utf-8") as f:
    json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

print("\nErgebnis gespeichert in: Output/test_plz_result.json")

"""
Test German recognition of foreign qualifications extraction.
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

# Test transcript with foreign qualification + German recognition
test_transcript = [
    {"speaker": "Agent", "text": "Guten Tag! Erzählen Sie mir von Ihrer Ausbildung."},
    {"speaker": "Applicant", "text": "Ich habe 2018 in der Türkei meine Ausbildung als Pflegefachmann abgeschlossen."},
    {"speaker": "Agent", "text": "Haben Sie eine deutsche Anerkennung?"},
    {"speaker": "Applicant", "text": "Ja, 2023 habe ich die deutsche Anerkennung vom Regierungspräsidium Stuttgart bekommen. Die haben gesagt, dass mein Abschluss gleichwertig ist mit dem deutschen Pflegefachmann."},
    {"speaker": "Agent", "text": "Das ist prima! Und wo haben Sie in der Türkei gelernt?"},
    {"speaker": "Applicant", "text": "An der Pflegeschule in Istanbul."},
]

# Test with metadata
test_metadata = {
    "conversation_id": "test_recognition_456",
    "candidate_first_name": "Mehmet",
    "candidate_last_name": "Yilmaz",
    "to_number": "+49 711 12345678"
}

print("=" * 70)
print("TEST: DEUTSCHE ANERKENNUNG AUSLÄNDISCHER ABSCHLÜSSE")
print("=" * 70)

print("\n1) Transkript:")
for i, turn in enumerate(test_transcript, 1):
    speaker_short = "A" if turn['speaker'] == "Agent" else "K"
    print(f"   [{speaker_short}{i}] {turn['text'][:70]}...")

print("\n2) TEMPORAL ENRICHER...")
enricher = TemporalEnricher()
enriched_transcript = enricher.enrich_transcript(test_transcript, use_mcp=False)
temporal_context = enricher.extract_temporal_context(enriched_transcript)

print("\n3) RESUME BUILDER (mit Anerkennungs-Extraktion)...")
builder = ResumeBuilder()
result = builder.build_resume(
    transcript=enriched_transcript,
    elevenlabs_metadata=test_metadata,
    temporal_context=temporal_context
)

print("\n" + "=" * 70)
print("ERGEBNIS:")
print("=" * 70)

print("\n[EDUCATIONS]")
for i, edu in enumerate(result.resume.educations, 1):
    print(f"\nEducation {i}:")
    print(f"  Company: {edu.company}")
    print(f"  Description: {edu.description}")
    print(f"  End: {edu.end}")

print("\n" + "=" * 70)
print("VALIDIERUNG:")
print("=" * 70)

# Expected: 2 educations
expected_count = 2
actual_count = len(result.resume.educations)

if actual_count == expected_count:
    print(f"✅ Anzahl Einträge: {actual_count} (erwartet: {expected_count})")
else:
    print(f"❌ Anzahl Einträge: {actual_count} (erwartet: {expected_count})")

# Check if first is original qualification
if result.resume.educations:
    first = result.resume.educations[0]
    has_turkey = "türkei" in (first.company or "").lower()
    has_pflege = "pflege" in first.description.lower()
    
    if has_turkey and has_pflege:
        print(f"✅ Education 1: Originalabschluss (Türkei)")
    else:
        print(f"❌ Education 1: Fehlt Türkei oder Pflege")
        print(f"   Company: {first.company}")
        print(f"   Description: {first.description}")

# Check if second is recognition
if len(result.resume.educations) >= 2:
    second = result.resume.educations[1]
    has_recognition = "anerkennung" in second.description.lower()
    has_authority = "regierungspräsidium" in (second.company or "").lower()
    
    if has_recognition and has_authority:
        print(f"✅ Education 2: Deutsche Anerkennung (Regierungspräsidium)")
    else:
        print(f"❌ Education 2: Fehlt Anerkennung oder Behörde")
        print(f"   Company: {second.company}")
        print(f"   Description: {second.description}")

print("\n" + "=" * 70)
if actual_count == 2:
    print("SUCCESS! 2 separate Einträge wurden korrekt erstellt!")
else:
    print(f"FEHLER! Erwartete 2 Einträge, bekam {actual_count}")
print("=" * 70)

# Save result
with open("Output/test_recognition_result.json", "w", encoding="utf-8") as f:
    json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

print("\nErgebnis gespeichert in: Output/test_recognition_result.json")

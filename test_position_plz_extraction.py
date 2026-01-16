"""
Test PLZ and Position extraction with improved prompts.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

import json
from resume_builder import ResumeBuilder

print("=" * 70)
print("TEST: PLZ & POSITION EXTRACTION (VERBESSERTE PROMPTS)")
print("=" * 70)

# Test transcript with PLZ and job description
test_transcript = [
    {
        "speaker": "B",
        "text": "Hallo, schön dass Sie Zeit haben. Erzählen Sie mir doch etwas über sich."
    },
    {
        "speaker": "A",
        "text": "Ja gerne. Ich bin 28 Jahre alt und wohne in 49536 Lotte. Ich arbeite seit 2021 als Konstrukteur bei Windmüller und Hölscher in Lengrich."
    },
    {
        "speaker": "B",
        "text": "Was sind Ihre Hauptaufgaben dort?"
    },
    {
        "speaker": "A",
        "text": "Ich mache Hardwarekonstruktion für Kundenanlagen, vor allem im Bereich Automatisierungstechnik. Ich integriere Kundenwünsche in die Anlagendesigns und bin auch im direkten Austausch mit Kunden für technische Beratung. Zusätzlich arbeite ich an Prozessoptimierung und Digitalisierungsprojekten."
    }
]

print("\nTranskript:")
for turn in test_transcript:
    speaker = "Kandidat" if turn['speaker'] == 'A' else "Recruiter"
    print(f"  [{speaker}]: {turn['text'][:80]}...")

print("\n" + "=" * 70)
print("RESUME-BUILDER AUFRUF (mit Claude Sonnet 4.5)...")
print("=" * 70)

builder = ResumeBuilder(prefer_claude=True)

try:
    applicant_resume = builder.build_resume(
        transcript=test_transcript,
        elevenlabs_metadata={"conversation_id": "test_plz_position_001"},
        temporal_context={"call_date": "2026-01-16", "call_year": 2026}
    )
    
    print("\n" + "=" * 70)
    print("ERGEBNIS:")
    print("=" * 70)
    
    # Check PLZ
    plz = applicant_resume.applicant.postal_code
    print(f"\nPLZ: {plz}")
    if plz == "49536":
        print("  PLZ KORREKT EXTRAHIERT!")
    elif plz:
        print(f"  PLZ FALSCH! Erwartet: 49536, Erhalten: {plz}")
    else:
        print("  PLZ FEHLT!")
    
    # Check Experiences
    print(f"\nExperiences: {len(applicant_resume.resume.experiences)}")
    
    for i, exp in enumerate(applicant_resume.resume.experiences, 1):
        print(f"\n  Experience {i}:")
        print(f"    Position: {exp.position}")
        print(f"    Company: {exp.company}")
        print(f"    Tasks: {exp.tasks[:100]}...")
        print(f"    Tasks Length: {len(exp.tasks)} Zeichen")
        
        # Validate position
        if exp.position:
            if any(vague in exp.position.lower() for vague in ['arbeit in', 'tätig in', 'im bereich']):
                print(f"    POSITION VAGE!")
            else:
                print(f"    POSITION OK!")
        else:
            print(f"    POSITION FEHLT!")
        
        # Validate tasks length
        if len(exp.tasks) >= 100:
            print(f"    TASKS LENGTH OK!")
        else:
            print(f"    TASKS ZU KURZ!")
    
    print("\n" + "=" * 70)
    
    # Save result
    output_path = "Output/test_plz_position_result.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(applicant_resume.dict(), f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\nErgebnis gespeichert: {output_path}")
    
    # Summary
    success = True
    if plz != "49536":
        success = False
        print("\nFEHLER: PLZ nicht korrekt extrahiert!")
    
    if len(applicant_resume.resume.experiences) == 0:
        success = False
        print("\nFEHLER: Keine Experiences extrahiert!")
    
    for exp in applicant_resume.resume.experiences:
        if not exp.position or any(vague in exp.position.lower() for vague in ['arbeit in', 'tätig in', 'im bereich']):
            success = False
            print(f"\nFEHLER: Position vage oder fehlend: {exp.position}")
        
        if len(exp.tasks) < 100:
            success = False
            print(f"\nFEHLER: Tasks zu kurz: {len(exp.tasks)} Zeichen")
    
    if success:
        print("\nSUCCESS! Alle Tests bestanden!")
    
    print("=" * 70)
    
except Exception as e:
    print(f"\nFEHLER: {e}")
    import traceback
    traceback.print_exc()

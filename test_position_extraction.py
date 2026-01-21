"""Test position extraction from real transcripts."""
import os
import sys
import json
from dotenv import load_dotenv

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from resume_builder import ResumeBuilder

# Load environment variables
load_dotenv()


def test_kita_transcript_position_extraction():
    """Test that position fields are correctly extracted from Kita transcript."""
    print("\n" + "="*70)
    print("TEST: Kita-Transcript Position Extraktion")
    print("="*70)
    
    # Load real transcript
    with open('Input/Transkript_beispiel.json', 'r', encoding='utf-8') as f:
        transcript = json.load(f)
    
    # Build resume
    builder = ResumeBuilder(prefer_claude=True)
    resume_result = builder.build_resume(transcript)
    
    print(f"\n✅ Applicant ID: {resume_result.applicant.id}")
    print(f"✅ Resume ID: {resume_result.resume.id}")
    print(f"\n📋 Experiences gefunden: {len(resume_result.resume.experiences)}")
    
    # Check each experience has position
    all_positions_present = True
    for i, exp in enumerate(resume_result.resume.experiences, start=1):
        print(f"\n--- Experience {i} ---")
        print(f"   Position: {exp.position}")
        print(f"   Company: {exp.company}")
        print(f"   Employment Type: {exp.employment_type}")
        print(f"   Start: {exp.start}")
        print(f"   End: {exp.end}")
        print(f"   Tasks: {exp.tasks[:100]}..." if len(exp.tasks) > 100 else f"   Tasks: {exp.tasks}")
        
        if not exp.position:
            print(f"   ❌ FEHLER: Position fehlt!")
            all_positions_present = False
        elif any(vague in exp.position.lower() for vague in ['arbeit in', 'tätig in', 'mitarbeiter bei']):
            print(f"   ⚠️ WARNUNG: Position ist vage!")
        else:
            print(f"   ✅ Position ist konkret!")
    
    print(f"\n📚 Educations gefunden: {len(resume_result.resume.educations)}")
    for i, edu in enumerate(resume_result.resume.educations, start=1):
        print(f"\n--- Education {i} ---")
        print(f"   Description: {edu.description}")
        print(f"   Company: {edu.company}")
        print(f"   End: {edu.end}")
    
    # Assertions
    assert len(resume_result.resume.experiences) > 0, "Keine Experiences extrahiert!"
    assert all_positions_present, "Nicht alle Experiences haben ein position-Feld!"
    
    print("\n" + "="*70)
    print("✅ TEST ERFOLGREICH: Alle Positionen korrekt extrahiert!")
    print("="*70)
    
    return resume_result


def test_elektrotechnik_transcript_position_extraction():
    """Test that position fields are correctly extracted from Elektrotechnik transcript."""
    print("\n" + "="*70)
    print("TEST: Elektrotechnik-Transcript Position Extraktion")
    print("="*70)
    
    # Load real transcript
    with open('Input2/Transkript_beispiel.json', 'r', encoding='utf-8') as f:
        transcript = json.load(f)
    
    # Build resume
    builder = ResumeBuilder(prefer_claude=True)
    resume_result = builder.build_resume(transcript)
    
    print(f"\n✅ Applicant ID: {resume_result.applicant.id}")
    print(f"✅ Resume ID: {resume_result.resume.id}")
    print(f"\n📋 Experiences gefunden: {len(resume_result.resume.experiences)}")
    
    # Check each experience has position
    all_positions_present = True
    expected_positions = ['Hardwarekonstrukteur', 'Konstrukteur', 'Werkstudent']
    
    for i, exp in enumerate(resume_result.resume.experiences, start=1):
        print(f"\n--- Experience {i} ---")
        print(f"   Position: {exp.position}")
        print(f"   Company: {exp.company}")
        print(f"   Employment Type: {exp.employment_type}")
        print(f"   Start: {exp.start}")
        print(f"   End: {exp.end}")
        print(f"   Tasks: {exp.tasks[:100]}..." if len(exp.tasks) > 100 else f"   Tasks: {exp.tasks}")
        
        if not exp.position:
            print(f"   ❌ FEHLER: Position fehlt!")
            all_positions_present = False
        elif any(vague in exp.position.lower() for vague in ['arbeit in', 'tätig in', 'mitarbeiter bei']):
            print(f"   ⚠️ WARNUNG: Position ist vage!")
        else:
            print(f"   ✅ Position ist konkret!")
        
        # Check if position contains expected keywords
        if exp.position and any(keyword.lower() in exp.position.lower() for keyword in expected_positions):
            print(f"   ✅ Position enthält erwarteten Begriff!")
    
    print(f"\n📚 Educations gefunden: {len(resume_result.resume.educations)}")
    for i, edu in enumerate(resume_result.resume.educations, start=1):
        print(f"\n--- Education {i} ---")
        print(f"   Description: {edu.description}")
        print(f"   Company: {edu.company}")
        print(f"   End: {edu.end}")
    
    # Assertions
    assert len(resume_result.resume.experiences) > 0, "Keine Experiences extrahiert!"
    assert all_positions_present, "Nicht alle Experiences haben ein position-Feld!"
    
    print("\n" + "="*70)
    print("✅ TEST ERFOLGREICH: Alle Positionen korrekt extrahiert!")
    print("="*70)
    
    return resume_result


def test_position_quality():
    """Test that extracted positions meet quality criteria."""
    print("\n" + "="*70)
    print("TEST: Position-Qualität prüfen")
    print("="*70)
    
    # Run both tests
    kita_result = test_kita_transcript_position_extraction()
    elektro_result = test_elektrotechnik_transcript_position_extraction()
    
    all_experiences = kita_result.resume.experiences + elektro_result.resume.experiences
    
    print(f"\n🔍 Qualitätsprüfung für {len(all_experiences)} Experiences:")
    
    vague_positions = []
    for exp in all_experiences:
        if exp.position:
            # Check for vague terms
            if any(vague in exp.position.lower() for vague in [
                'arbeit in', 'tätig in', 'tätig als', 'im bereich',
                'mitarbeiter bei', 'beschäftigt'
            ]):
                vague_positions.append(exp.position)
    
    if vague_positions:
        print(f"\n⚠️ {len(vague_positions)} vage Positionen gefunden:")
        for pos in vague_positions:
            print(f"   - {pos}")
    else:
        print(f"\n✅ Alle Positionen sind konkret und präzise!")
    
    print("\n" + "="*70)
    print(f"ZUSAMMENFASSUNG:")
    print(f"  Total Experiences: {len(all_experiences)}")
    print(f"  Vage Positionen: {len(vague_positions)}")
    print(f"  Qualität: {100 - (len(vague_positions) / len(all_experiences) * 100):.1f}%")
    print("="*70)
    
    # Write results to file for inspection
    output = {
        "kita": {
            "applicant": kita_result.applicant.model_dump(),
            "resume": kita_result.resume.model_dump()
        },
        "elektrotechnik": {
            "applicant": elektro_result.applicant.model_dump(),
            "resume": elektro_result.resume.model_dump()
        }
    }
    
    with open('Output/test_position_extraction_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n💾 Ergebnisse gespeichert in: Output/test_position_extraction_results.json")


if __name__ == "__main__":
    try:
        test_position_quality()
        print("\n🎉 ALLE TESTS BESTANDEN!")
    except AssertionError as e:
        print(f"\n❌ TEST FEHLGESCHLAGEN: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ FEHLER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

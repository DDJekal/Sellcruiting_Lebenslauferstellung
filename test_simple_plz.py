"""Simple test for PLZ at end."""
import sys
import os

print("Starting test...")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
print("Path inserted...")

try:
    from dotenv import load_dotenv
    print("dotenv imported...")
    load_dotenv()
    print("dotenv loaded...")
    
    from resume_builder import ResumeBuilder
    print("ResumeBuilder imported...")
    
    test_transcript = [
        {"speaker": "B", "text": "Hallo, wo wohnen Sie?"},
        {"speaker": "A", "text": "In Lotte, das ist 49536."}
    ]
    
    print(f"Testing with transcript: {test_transcript}")
    
    builder = ResumeBuilder(prefer_claude=True)
    print("Builder created...")
    
    result = builder.build_resume(
        transcript=test_transcript,
        elevenlabs_metadata={"conversation_id": "test"},
        temporal_context={"call_date": "2026-01-16", "call_year": 2026}
    )
    
    print(f"PLZ: {result.applicant.postal_code}")
    print(f"City: {result.resume.city}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

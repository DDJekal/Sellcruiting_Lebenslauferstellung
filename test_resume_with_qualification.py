"""Test script to verify qualification summary in resume."""
import os
import sys
import json
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from validator import Validator
from resume_builder import ResumeBuilder
from models import MandantenConfig, FilledProtocol

def main():
    """Test the qualification summary in resume."""
    print("=" * 80)
    print("TEST: QUALIFICATION SUMMARY IM RESUME")
    print("=" * 80)
    
    # Load environment variables
    load_dotenv()
    
    # Load existing filled protocol
    filled_protocol_path = Path("Output/filled_protocol_template_63.json")
    if not filled_protocol_path.exists():
        print(f"ERROR: Filled protocol not found: {filled_protocol_path}")
        return
    
    with open(filled_protocol_path, "r", encoding="utf-8") as f:
        filled_protocol_data = json.load(f)
    
    # Load config
    config_path = Path("config/mandanten/template_63.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    
    mandanten_config = MandantenConfig(**config_data)
    
    # Parse filled protocol
    filled_protocol = FilledProtocol(**filled_protocol_data)
    
    # Load transcript for resume builder
    transcript_path = Path("Input2/Transkript_beispiel.json")
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)
    
    # Initialize modules
    validator = Validator()
    resume_builder = ResumeBuilder()
    
    print("\n[1] Evaluiere Qualifikation...")
    qualification = validator.evaluate_qualification(filled_protocol, mandanten_config)
    print(f"   -> {qualification['summary']}")
    
    print("\n[2] Erstelle Resume...")
    applicant_resume = resume_builder.build_resume(
        transcript=transcript,
        elevenlabs_metadata=None,
        temporal_context=filled_protocol_data.get("temporal_context")
    )
    
    print("\n[3] Fuege Qualification Summary und Status zum Resume hinzu...")
    applicant_resume.resume.summary = qualification["summary"]
    applicant_resume.resume.qualified = qualification["is_qualified"]
    
    # Save resume with qualification
    output_path = Path("Output/resume_with_qualification.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(applicant_resume.model_dump(), f, indent=2, ensure_ascii=False)
    
    print(f"\n[4] Resume gespeichert: {output_path}")
    
    # Print resume excerpt
    print("\n" + "=" * 80)
    print("RESUME AUSZUG")
    print("=" * 80)
    print(f"\nApplicant ID: {applicant_resume.applicant.id}")
    print(f"Name: {applicant_resume.applicant.first_name} {applicant_resume.applicant.last_name}")
    print(f"\nQUALIFICATION:")
    print(f"  Qualified: {applicant_resume.resume.qualified}")
    print(f"  Summary: {applicant_resume.resume.summary}")
    print(f"\nExperiences: {len(applicant_resume.resume.experiences)}")
    print(f"Educations: {len(applicant_resume.resume.educations)}")
    
    print("\n" + "=" * 80)
    print("[OK] TEST ABGESCHLOSSEN")
    print("=" * 80)

if __name__ == "__main__":
    main()

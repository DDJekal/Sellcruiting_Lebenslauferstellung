"""Test script for qualification evaluation."""
import os
import sys
import json
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from validator import Validator
from models import MandantenConfig, FilledProtocol

def main():
    """Test the qualification evaluation."""
    print("=" * 80)
    print("TEST: QUALIFIKATIONS-EVALUATION")
    print("=" * 80)
    
    # Load environment variables
    load_dotenv()
    
    # Load existing filled protocol
    filled_protocol_path = Path("Output/filled_protocol_template_63.json")
    if not filled_protocol_path.exists():
        print(f"ERROR: Filled protocol not found: {filled_protocol_path}")
        print("Bitte führe zuerst main.py aus, um ein Protocol zu generieren.")
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
    
    # Initialize validator
    validator = Validator()
    
    # Evaluate qualification
    print("\n[1] Evaluiere Qualifikation...")
    qualification = validator.evaluate_qualification(filled_protocol, mandanten_config)
    
    # Print results
    print("\n" + "=" * 80)
    print("ERGEBNIS")
    print("=" * 80)
    
    print(f"\n>> {qualification['summary']}")
    print(f"\nStatus: {'QUALIFIZIERT' if qualification['is_qualified'] else 'NICHT QUALIFIZIERT'}")
    print(f"Erfuellt: {qualification['fulfilled_count']}/{qualification['total_count']} Kriterien")
    
    if qualification['errors']:
        print(f"\nFehlende Kriterien:")
        for error in qualification['errors']:
            print(f"   - {error}")
    
    print(f"\nDetails zu allen Kriterien:")
    for criterion in qualification['criteria_details']:
        status = "[OK]" if criterion['fulfilled'] else "[FEHLT]"
        print(f"\n   {status} Prompt {criterion['prompt_id']}")
        print(f"      Frage: {criterion['question']}")
        print(f"      Erwartet: {criterion['expected']}")
        print(f"      Tatsaechlich: {criterion['actual']}")
        print(f"      Confidence: {criterion['confidence']:.2f}")
    
    # Save qualification result
    output_path = Path("Output/qualification_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(qualification, f, indent=2, ensure_ascii=False)
    
    print(f"\nErgebnis gespeichert: {output_path}")
    
    print("\n" + "=" * 80)
    print("[OK] TEST ABGESCHLOSSEN")
    print("=" * 80)

if __name__ == "__main__":
    main()

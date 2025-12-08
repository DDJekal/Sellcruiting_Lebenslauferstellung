"""Main script to test protocol filling system."""
import os
import json
import yaml
from pathlib import Path
from dotenv import load_dotenv

from src.type_enricher import TypeEnricher
from src.config_parser import ConfigParser
from src.extractor import Extractor
from src.mapper import Mapper
from src.validator import Validator
from src.config_generator import ConfigGenerator
from src.models import MandantenConfig
from src.elevenlabs_transformer import ElevenLabsTransformer
from src.temporal_enricher import TemporalEnricher
from src.resume_builder import ResumeBuilder


def main():
    """Run the protocol filling pipeline."""
    print("=" * 80)
    print("PROTOKOLL-BEFÜLLUNGS-SYSTEM - TEST")
    print("=" * 80)
    
    # Load environment variables
    load_dotenv()
    
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY nicht in .env gefunden!")
        print("Bitte erstelle .env Datei mit deinem API-Key.")
        return
    
    # Load input files
    print("\n[1] Lade Input-Dateien...")
    protocol_path = Path("Input2/Gesprächsprotokollbeispiel_2.json")
    
    # Internes Format (längeres Beispiel):
    transcript_path = Path("Input2/Transkript_beispiel.json")
    # Für ElevenLabs Webhook Test:
    # transcript_path = Path("Input2/elevenlabs_webhook_test.json")
    
    with open(protocol_path, "r", encoding="utf-8") as f:
        protocol = json.load(f)
    print(f"   [OK] Protokoll geladen: {protocol['name']}")
    
    # Check if transcript is ElevenLabs format or internal format
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_raw = json.load(f)
    
    call_timestamp = None  # Will be extracted from ElevenLabs if available
    metadata = {}
    
    # Detect format and transform if necessary
    if isinstance(transcript_raw, dict) and transcript_raw.get("type") == "post_call_transcription":
        print(f"   [INFO] ElevenLabs-Webhook-Format erkannt, transformiere...")
        transformer = ElevenLabsTransformer()
        transcript = transformer.transform(transcript_raw)
        metadata = transformer.extract_metadata(transcript_raw)
        
        # Get call timestamp for temporal enrichment
        call_timestamp = metadata.get('start_time_unix_secs')
        
        print(f"   [OK] Transkript transformiert: {len(transcript)} Turns")
        print(f"   [INFO] Kandidat: {metadata.get('candidate_first_name')} {metadata.get('candidate_last_name')}")
        print(f"   [INFO] Firma: {metadata.get('company_name')}")
        print(f"   [INFO] Rolle: {metadata.get('campaign_role_title')}")
        print(f"   [INFO] Gesprächsdauer: {metadata.get('call_duration_secs')}s")
        print(f"   [INFO] Status: {metadata.get('call_successful')}")
        if call_timestamp:
            from datetime import datetime
            print(f"   [INFO] Call-Zeitpunkt: {datetime.fromtimestamp(call_timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
    elif isinstance(transcript_raw, list):
        print(f"   [OK] Internes Transkript-Format erkannt")
        transcript = transcript_raw
        print(f"   [OK] Transkript geladen: {len(transcript)} Turns")
    else:
        print(f"   [ERROR] Unbekanntes Transkript-Format!")
        return
    
    # Temporal enrichment
    print("\n[1b] Reichere Transkript mit zeitlichem Kontext an...")
    use_mcp = os.getenv('USE_MCP_TEMPORAL_VALIDATION', 'false').lower() == 'true'
    temporal_enricher = TemporalEnricher(reference_timestamp=call_timestamp)
    transcript = temporal_enricher.enrich_transcript(transcript, use_mcp=use_mcp)
    temporal_context = temporal_enricher.extract_temporal_context(transcript)
    
    print(f"   [OK] Temporale Anreicherung abgeschlossen")
    print(f"   [INFO] Referenzdatum: {temporal_context['call_date']}")
    if temporal_context['mentioned_years']:
        print(f"   [INFO] Erwähnte Jahre: {temporal_context['mentioned_years']}")
    if use_mcp:
        print(f"   [INFO] MCP-Validierung: aktiviert")
    else:
        print(f"   [INFO] MCP-Validierung: deaktiviert (nur dateparser)")
    
    # Auto-generate or load config based on template_id
    template_id = protocol.get("id")
    config_path = Path(f"config/mandanten/template_{template_id}.yaml")
    
    if not config_path.exists():
        print(f"\n[2] Config nicht gefunden, generiere automatisch...")
        config_generator = ConfigGenerator()
        config_data = config_generator.generate_config(protocol, output_path=config_path)
        mandanten_config = MandantenConfig(**config_data)
        print(f"   [OK] Config automatisch generiert: {config_path}")
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        mandanten_config = MandantenConfig(**config_data)
        print(f"   [OK] Mandanten-Config geladen: {mandanten_config.mandant_id}")
    
    # Initialize modules
    print("\n[3] Initialisiere Module...")
    type_enricher = TypeEnricher()
    config_parser = ConfigParser()
    extractor = Extractor()
    mapper = Mapper()
    validator = Validator()
    resume_builder = ResumeBuilder()
    print("   [OK] Alle Module initialisiert")
    
    # Step 1: Infer shadow types
    print("\n[4] Inferiere Shadow-Types...")
    shadow_types = type_enricher.infer_types(protocol, mandanten_config)
    print(f"   [OK] {len(shadow_types)} Shadow-Types inferiert")
    
    # Print some shadow types
    for prompt_id, shadow_type in list(shadow_types.items())[:5]:
        print(f"      Prompt {prompt_id}: {shadow_type.inferred_type.value} (confidence: {shadow_type.confidence:.2f})")
    
    # Step 2: Extract grounding from "Weitere Informationen" page
    print("\n[5] Extrahiere Grounding-Infos...")
    weitere_info_page = next((p for p in protocol["pages"] if p["name"] == "Weitere Informationen"), None)
    extracted_grounding = {}
    if weitere_info_page:
        extracted_grounding = config_parser.extract_grounding(weitere_info_page["prompts"])
    
    # Merge with config grounding and add temporal context
    grounding = {**mandanten_config.grounding, **extracted_grounding}
    grounding['temporal_context'] = temporal_context
    
    # Optionally add ElevenLabs metadata to grounding
    if metadata:
        grounding['elevenlabs_metadata'] = metadata
    
    print(f"   [OK] Grounding extrahiert:")
    for key, value in list(grounding.items())[:5]:  # Show first 5 non-metadata items
        if key not in ['temporal_context', 'elevenlabs_metadata']:
            print(f"      {key}: {value}")
    print(f"      temporal_context: {temporal_context['call_date']}")
    
    # Step 3: Extract answers from transcript
    print("\n[6] Extrahiere Antworten aus Transkript (LLM-Call)...")
    print("   [WAIT] Dies kann 10-30 Sekunden dauern...")
    
    # Collect all prompts that need filling
    all_prompts = []
    for page in protocol["pages"]:
        all_prompts.extend(page["prompts"])
    
    extracted_answers = extractor.extract(transcript, shadow_types, grounding, all_prompts)
    print(f"   [OK] {len(extracted_answers)} Prompts befuellt")
    
    # Step 4: Map to filled protocol structure
    print("\n[7] Mappe zu FilledProtocol-Struktur...")
    filled_protocol = mapper.map_answers(protocol, shadow_types, extracted_answers)
    print(f"   [OK] {len(filled_protocol.pages)} Seiten gemappt")
    
    # Step 5: Apply implicit defaults
    print("\n[8] Wende implizite Defaults an...")
    filled_protocol = validator.apply_implicit_defaults(filled_protocol, mandanten_config)
    print(f"   [OK] {len(mandanten_config.implicit_defaults)} Implicit-Default-Regeln angewendet")
    
    # Step 6: Apply routing rules
    print("\n[9] Wende Routing-Engine an...")
    filled_protocol = validator.apply_routing_rules(filled_protocol, mandanten_config)
    print(f"   [OK] {len(mandanten_config.routing_rules)} Routing-Regeln angewendet")
    
    # Step 7: Validate must-criteria
    print("\n[10] Validiere Muss-Kriterien...")
    errors = validator.validate_must_criteria(filled_protocol, mandanten_config)
    if errors:
        print(f"   [WARN] {len(errors)} Validierungs-Fehler:")
        for error in errors:
            print(f"      - {error}")
    else:
        print("   [OK] Alle Muss-Kriterien erfuellt")
    
    # Step 8: Write output
    print("\n[11] Schreibe Output...")
    output_dir = Path("Output")
    output_dir.mkdir(exist_ok=True)
    
    # Include metadata in output
    output_data = filled_protocol.model_dump()
    if metadata:
        output_data['elevenlabs_metadata'] = metadata
    output_data['temporal_context'] = temporal_context
    
    # Use template_id in filename to avoid overwriting
    output_filename = f"filled_protocol_template_{template_id}.json"
    output_path = output_dir / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"   [OK] Protocol Output geschrieben: {output_path}")
    
    # Step 9: Build and write resume
    print("\n[12] Erstelle strukturierten Lebenslauf...")
    applicant_resume = resume_builder.build_resume(
        transcript=transcript,
        elevenlabs_metadata=metadata,
        temporal_context=temporal_context
    )
    
    # Write resume output
    resume_filename = f"resume_{applicant_resume.applicant.id}.json"
    resume_path = output_dir / resume_filename
    with open(resume_path, "w", encoding="utf-8") as f:
        json.dump(applicant_resume.model_dump(), f, indent=2, ensure_ascii=False)
    print(f"   [OK] Resume Output geschrieben: {resume_path}")
    print(f"   [INFO] Applicant ID: {applicant_resume.applicant.id}")
    print(f"   [INFO] {len(applicant_resume.resume.experiences)} Experiences")
    print(f"   [INFO] {len(applicant_resume.resume.educations)} Educations")
    
    # Step 8: Print summary
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    
    total_prompts = sum(len(page.prompts) for page in filled_protocol.pages)
    filled_prompts = sum(
        1 for page in filled_protocol.pages
        for prompt in page.prompts
        if prompt.answer.confidence > 0 or prompt.answer.checked is not None or prompt.answer.value
    )
    
    avg_confidence = 0
    confidence_count = 0
    for page in filled_protocol.pages:
        for prompt in page.prompts:
            if prompt.answer.confidence > 0:
                avg_confidence += prompt.answer.confidence
                confidence_count += 1
    
    if confidence_count > 0:
        avg_confidence /= confidence_count
    
    print(f"\nPrompts insgesamt: {total_prompts}")
    print(f"Prompts befüllt: {filled_prompts}")
    print(f"Durchschnittliche Confidence: {avg_confidence:.2f}")
    
    if metadata:
        print(f"\nElevenLabs Call Info:")
        print(f"  Kandidat: {metadata.get('candidate_first_name')} {metadata.get('candidate_last_name')}")
        print(f"  Rolle: {metadata.get('campaign_role_title')}")
        print(f"  Standort: {metadata.get('campaign_location')}")
        print(f"  Dauer: {metadata.get('call_duration_secs')}s")
        print(f"  Erfolg: {metadata.get('call_successful')}")
        print(f"  Konversation-ID: {metadata.get('conversation_id')}")
    
    print(f"\nTemporal Context:")
    print(f"  Referenzdatum: {temporal_context['call_date']}")
    print(f"  Erwähnte Jahre: {temporal_context['mentioned_years']}")
    
    # Print some examples
    print("\n" + "-" * 80)
    print("BEISPIEL-ANTWORTEN:")
    print("-" * 80)
    
    for page in filled_protocol.pages:
        if page.name == "Der Bewerber erfüllt folgende Kriterien:":
            for prompt in page.prompts[:3]:  # First 3
                print(f"\nPrompt {prompt.id}: {prompt.question[:60]}...")
                print(f"  Type: {prompt.inferred_type.value}")
                print(f"  Checked: {prompt.answer.checked}")
                print(f"  Value: {prompt.answer.value}")
                print(f"  Confidence: {prompt.answer.confidence:.2f}")
                if prompt.answer.evidence:
                    print(f"  Evidence: {len(prompt.answer.evidence)} Snippet(s)")
                if prompt.answer.notes:
                    print(f"  Notes: {prompt.answer.notes}")
    
    print("\n" + "=" * 80)
    print("[OK] TEST ABGESCHLOSSEN - DUAL OUTPUT ERSTELLT")
    print("=" * 80)
    print(f"\n📄 Protocol: {output_path}")
    print(f"👤 Resume: {resume_path}")


if __name__ == "__main__":
    main()


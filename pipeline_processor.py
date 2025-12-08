"""Pipeline processor wrapper for webhook integration."""
import os
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from src.elevenlabs_transformer import ElevenLabsTransformer
from src.temporal_enricher import TemporalEnricher
from src.type_enricher import TypeEnricher
from src.config_parser import ConfigParser
from src.config_generator import ConfigGenerator
from src.extractor import Extractor
from src.mapper import Mapper
from src.validator import Validator
from src.resume_builder import ResumeBuilder
from src.models import MandantenConfig


def process_elevenlabs_call(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process ElevenLabs webhook through complete pipeline.
    
    Args:
        webhook_data: Full ElevenLabs webhook payload
        
    Returns:
        Dict with processing results including applicant_id, resume, protocol
    """
    # Transform ElevenLabs data
    transformer = ElevenLabsTransformer()
    transcript = transformer.transform(webhook_data)
    metadata = transformer.extract_metadata(webhook_data)
    
    conversation_id = metadata.get('conversation_id')
    call_timestamp = metadata.get('start_time_unix_secs')
    
    # Temporal enrichment
    use_mcp = os.getenv('USE_MCP_TEMPORAL_VALIDATION', 'false').lower() == 'true'
    temporal_enricher = TemporalEnricher(reference_timestamp=call_timestamp)
    transcript = temporal_enricher.enrich_transcript(transcript, use_mcp=use_mcp)
    temporal_context = temporal_enricher.extract_temporal_context(transcript)
    
    # Load or generate protocol template
    # For now, we'll use a default template ID
    # TODO: Make this configurable via webhook metadata
    protocol_template_id = int(os.getenv('DEFAULT_PROTOCOL_TEMPLATE_ID', '63'))
    
    protocol_path = Path(f"Input2/Gesprächsprotokollbeispiel_2.json")
    if not protocol_path.exists():
        raise FileNotFoundError(f"Protocol template not found: {protocol_path}")
    
    with open(protocol_path, 'r', encoding='utf-8') as f:
        protocol = json.load(f)
    
    # Load or generate config
    config_path = Path(f"config/mandanten/template_{protocol_template_id}.yaml")
    if not config_path.exists():
        config_generator = ConfigGenerator()
        config_data = config_generator.generate_config(protocol, output_path=config_path)
        mandanten_config = MandantenConfig(**config_data)
    else:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        mandanten_config = MandantenConfig(**config_data)
    
    # Initialize modules
    type_enricher = TypeEnricher()
    config_parser = ConfigParser()
    extractor = Extractor()
    mapper = Mapper()
    validator = Validator()
    resume_builder = ResumeBuilder()
    
    # Infer shadow types
    shadow_types = type_enricher.infer_types(protocol, mandanten_config)
    
    # Extract grounding
    weitere_info_page = next((p for p in protocol["pages"] if p["name"] == "Weitere Informationen"), None)
    extracted_grounding = {}
    if weitere_info_page:
        extracted_grounding = config_parser.extract_grounding(weitere_info_page["prompts"])
    
    grounding = {
        **mandanten_config.grounding,
        **extracted_grounding,
        'temporal_context': temporal_context,
        'elevenlabs_metadata': metadata
    }
    
    # Extract answers
    all_prompts = []
    for page in protocol["pages"]:
        all_prompts.extend(page["prompts"])
    
    extracted_answers = extractor.extract(transcript, shadow_types, grounding, all_prompts)
    
    # Map to filled protocol
    filled_protocol = mapper.map_answers(protocol, shadow_types, extracted_answers)
    
    # Apply implicit defaults and routing
    filled_protocol = validator.apply_implicit_defaults(filled_protocol, mandanten_config)
    filled_protocol = validator.apply_routing_rules(filled_protocol, mandanten_config)
    
    # Build resume
    applicant_resume = resume_builder.build_resume(
        transcript=transcript,
        elevenlabs_metadata=metadata,
        temporal_context=temporal_context
    )
    
    # Save outputs (optional, for debugging)
    output_dir = Path("Output")
    output_dir.mkdir(exist_ok=True)
    
    # Save protocol
    protocol_output = filled_protocol.model_dump()
    protocol_output['elevenlabs_metadata'] = metadata
    protocol_output['temporal_context'] = temporal_context
    
    protocol_filename = f"filled_protocol_{conversation_id}.json"
    with open(output_dir / protocol_filename, 'w', encoding='utf-8') as f:
        json.dump(protocol_output, f, indent=2, ensure_ascii=False)
    
    # Save resume
    resume_filename = f"resume_{applicant_resume.applicant.id}.json"
    with open(output_dir / resume_filename, 'w', encoding='utf-8') as f:
        json.dump(applicant_resume.model_dump(), f, indent=2, ensure_ascii=False)
    
    # Return result
    return {
        "conversation_id": conversation_id,
        "applicant_id": applicant_resume.applicant.id,
        "resume_id": applicant_resume.resume.id,
        "applicant": applicant_resume.applicant.model_dump(),
        "resume": applicant_resume.resume.model_dump(),
        "protocol": protocol_output,
        "experiences_count": len(applicant_resume.resume.experiences),
        "educations_count": len(applicant_resume.resume.educations),
        "timestamp": datetime.utcnow().isoformat()
    }


"""Pipeline processor wrapper for webhook integration."""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from elevenlabs_transformer import ElevenLabsTransformer
from temporal_enricher import TemporalEnricher
from type_enricher import TypeEnricher
from config_parser import ConfigParser
from config_generator import ConfigGenerator
from extractor import Extractor
from mapper import Mapper
from validator import Validator
from resume_builder import ResumeBuilder
from questionnaire_client import QuestionnaireClient
from models import MandantenConfig

logger = logging.getLogger(__name__)


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
    campaign_id = metadata.get('campaign_id')
    
    logger.info(f"Processing call: conversation_id={conversation_id}, campaign_id={campaign_id}")
    
    # Temporal enrichment
    use_mcp = os.getenv('USE_MCP_TEMPORAL_VALIDATION', 'false').lower() == 'true'
    temporal_enricher = TemporalEnricher(reference_timestamp=call_timestamp)
    transcript = temporal_enricher.enrich_transcript(transcript, use_mcp=use_mcp)
    temporal_context = temporal_enricher.extract_temporal_context(transcript)
    
    # Load protocol template
    # Priority: 1. API (if campaign_id available), 2. Local fallback
    protocol = None
    protocol_source = "unknown"
    
    if campaign_id:
        # Try to fetch questionnaire from API
        try:
            questionnaire_client = QuestionnaireClient()
            protocol = questionnaire_client.get_questionnaire_sync(campaign_id)
            protocol_source = f"api_campaign_{campaign_id}"
            logger.info(f"Loaded protocol from API for campaign_id={campaign_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch questionnaire from API for campaign {campaign_id}: {e}")
            logger.info("Falling back to local protocol template")
    
    # Fallback to local protocol if API failed or no campaign_id
    if not protocol:
        protocol_template_id = int(os.getenv('DEFAULT_PROTOCOL_TEMPLATE_ID', '63'))
        protocol_path = Path(f"Input2/Gesprächsprotokollbeispiel_2.json")
        
        if not protocol_path.exists():
            raise FileNotFoundError(f"Protocol template not found: {protocol_path}")
        
        with open(protocol_path, 'r', encoding='utf-8') as f:
            protocol = json.load(f)
        
        protocol_source = f"local_template_{protocol_template_id}"
        logger.info(f"Loaded local protocol template: {protocol_template_id}")
    
    # Load or generate config
    protocol_id = protocol.get("id", 63)
    config_path = Path(f"config/mandanten/template_{protocol_id}.yaml")
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
    protocol_output['protocol_source'] = protocol_source
    protocol_output['campaign_id'] = campaign_id
    
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
        "campaign_id": campaign_id,
        "protocol_source": protocol_source,
        "applicant_id": applicant_resume.applicant.id,
        "resume_id": applicant_resume.resume.id,
        "applicant": applicant_resume.applicant.model_dump(),
        "resume": applicant_resume.resume.model_dump(),
        "protocol": protocol_output,
        "experiences_count": len(applicant_resume.resume.experiences),
        "educations_count": len(applicant_resume.resume.educations),
        "timestamp": datetime.utcnow().isoformat()
    }


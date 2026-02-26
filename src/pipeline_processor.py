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
from qualification_matcher import QualificationMatcher
from questionnaire_client import QuestionnaireClient
from questionnaire_transformer import QuestionnaireTransformer
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
    original_protocol_metadata = {}  # Store original metadata from HOC
    
    if campaign_id:
        # Try to fetch transcript (Gesprächsprotokoll) from HOC API
        try:
            questionnaire_client = QuestionnaireClient()
            api_transcript = questionnaire_client.get_questionnaire_sync(campaign_id)
            
            # Store original metadata (created_on, updated_on, etc.)
            original_protocol_metadata = {
                "id": api_transcript.get("id"),
                "name": api_transcript.get("name"),
                "created_on": api_transcript.get("created_on"),
                "updated_on": api_transcript.get("updated_on")
            }
            
            # Store page/prompt metadata
            for page in api_transcript.get("pages", []):
                page_meta = {
                    "created_on": page.get("created_on"),
                    "updated_on": page.get("updated_on")
                }
                original_protocol_metadata[f"page_{page['id']}"] = page_meta
                
                for prompt in page.get("prompts", []):
                    prompt_meta = {
                        "information": prompt.get("information"),
                        "is_template": prompt.get("is_template"),
                        "created_on": prompt.get("created_on"),
                        "updated_on": prompt.get("updated_on"),
                        "type": prompt.get("type")  # Original type from HOC
                    }
                    original_protocol_metadata[f"prompt_{prompt['id']}"] = prompt_meta
            
            # Transform API format to internal format
            transformer = QuestionnaireTransformer()
            protocol = transformer.transform(api_transcript, campaign_id=campaign_id)
            
            protocol_source = f"api_campaign_{campaign_id}"
            logger.info(f"Loaded and transformed transcript from HOC API for campaign_id={campaign_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch transcript from API for campaign {campaign_id}: {e}")
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
    qualification_matcher = QualificationMatcher()  # NEU: Smart Matcher
    
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
    
    # Build resume BEFORE enrichment (unstrukturierte Extraktion)
    applicant_resume = resume_builder.build_resume(
        transcript=transcript,
        elevenlabs_metadata=metadata,
        temporal_context=temporal_context
    )
    
    # Enrich protocol with resume data (Smart Matching)
    logger.info("Enriching protocol with resume data (Smart Matching)...")
    filled_protocol = qualification_matcher.enrich_protocol_with_resume(
        filled_protocol=filled_protocol,
        resume=applicant_resume.resume,
        confidence_threshold=0.90
    )
    
    # Apply routing rules (implicit defaults REMOVED - no longer used)
    # filled_protocol = validator.apply_implicit_defaults(filled_protocol, mandanten_config)
    filled_protocol = validator.apply_routing_rules(filled_protocol, mandanten_config)
    
    # Evaluate qualification (jetzt mit enriched protocol + Anerkennung!)
    qualification_evaluation = validator.evaluate_qualification(
        filled_protocol, 
        mandanten_config,
        anerkennung_status=applicant_resume.resume.anerkennung_status
    )
    
    # Add qualification summary and status to resume
    applicant_resume.resume.summary = qualification_evaluation["summary"]
    applicant_resume.resume.qualified = qualification_evaluation["is_qualified"]
    
    # Save outputs (optional, for debugging)
    output_dir = Path("Output")
    output_dir.mkdir(exist_ok=True)
    
    # 1. Save minimal protocol (preserving HOC metadata)
    protocol_minimal = {
        "id": filled_protocol.protocol_id,
        "name": filled_protocol.protocol_name,
        "created_on": original_protocol_metadata.get("created_on"),
        "updated_on": original_protocol_metadata.get("updated_on"),
        "campaign_id": campaign_id,
        "conversation_id": conversation_id,
        "pages": []
    }
    
    for page in filled_protocol.pages:
        page_meta = original_protocol_metadata.get(f"page_{page.id}", {})
        minimal_prompts = []
        
        for prompt in page.prompts:
            prompt_meta = original_protocol_metadata.get(f"prompt_{prompt.id}", {})
            
            minimal_prompt = {
                "id": prompt.id,
                "question": prompt.question,
                "information": prompt_meta.get("information"),
                "position": len(minimal_prompts) + 1,
                "checked": prompt.answer.checked if prompt.answer else None,
                "is_template": prompt_meta.get("is_template", False),
                "created_on": prompt_meta.get("created_on"),
                "updated_on": prompt_meta.get("updated_on"),
                "type": prompt_meta.get("type", prompt.inferred_type.value if prompt.inferred_type else None)
            }
            minimal_prompts.append(minimal_prompt)
        
        minimal_page = {
            "id": page.id,
            "name": page.name,
            "position": len(protocol_minimal["pages"]) + 1,
            "created_on": page_meta.get("created_on"),
            "updated_on": page_meta.get("updated_on"),
            "prompts": minimal_prompts
        }
        protocol_minimal["pages"].append(minimal_page)
    
    protocol_filename = f"protocol_{conversation_id}.json"
    with open(output_dir / protocol_filename, 'w', encoding='utf-8') as f:
        json.dump(protocol_minimal, f, indent=2, ensure_ascii=False)
    
    # 2. Save resume (unchanged)
    resume_filename = f"resume_{applicant_resume.applicant.id}.json"
    with open(output_dir / resume_filename, 'w', encoding='utf-8') as f:
        json.dump(applicant_resume.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 3. Save metadata (NEW: all metadata in separate file)
    metadata_filename = f"metadata_{conversation_id}.json"
    metadata_output = {
        "conversation_id": conversation_id,
        "campaign_id": campaign_id,
        "applicant_id": applicant_resume.applicant.id,
        "protocol_source": protocol_source,
        "qualification": qualification_evaluation,  # NEW: Include qualification
        "elevenlabs": metadata,
        "temporal_context": temporal_context,
        "processing": {
            "timestamp": datetime.utcnow().isoformat(),
            "experiences_count": len(applicant_resume.resume.experiences),
            "educations_count": len(applicant_resume.resume.educations),
            "protocol_pages_count": len(filled_protocol.pages),
            "protocol_prompts_count": sum(len(p.prompts) for p in filled_protocol.pages)
        },
        "files": {
            "protocol": protocol_filename,
            "resume": resume_filename,
            "metadata": metadata_filename
        }
    }
    with open(output_dir / metadata_filename, 'w', encoding='utf-8') as f:
        json.dump(metadata_output, f, indent=2, ensure_ascii=False)
    
    # Return result
    return {
        "conversation_id": conversation_id,
        "campaign_id": campaign_id,
        "protocol_source": protocol_source,
        "qualification": qualification_evaluation,  # NEW: Qualification evaluation
        "applicant_id": applicant_resume.applicant.id,
        "resume_id": applicant_resume.resume.id,
        "applicant": applicant_resume.applicant.model_dump(),
        "resume": applicant_resume.resume.model_dump(),
        "protocol_minimal": protocol_minimal,  # Minimal protocol for HOC (checked only)
        "metadata": metadata_output,           # Full metadata for HOC
        "experiences_count": len(applicant_resume.resume.experiences),
        "educations_count": len(applicant_resume.resume.educations),
        "timestamp": datetime.utcnow().isoformat(),
        "files": {
            "protocol": protocol_filename,
            "resume": resume_filename,
            "metadata": metadata_filename
        }
    }


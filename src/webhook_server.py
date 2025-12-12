"""FastAPI Webhook Server for ElevenLabs → Processing Pipeline → HOC."""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="KI-Sellcruiting Pipeline",
    description="ElevenLabs Webhook → Protocol Filling → Resume Generation → HOC API",
    version="1.0.0"
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ki-sellcruiting-pipeline",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Detailed health check with environment validation."""
    health = {
        "status": "healthy",
        "checks": {
            "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "hoc_api_configured": bool(os.getenv("HOC_API_URL")),
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Check if critical dependencies are available
    if not health["checks"]["openai_api_key"]:
        health["status"] = "degraded"
        health["warning"] = "OPENAI_API_KEY not configured"
    
    return health


@app.post("/elevenlabs/posthook")
async def elevenlabs_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receive ElevenLabs post_call_transcription webhook.
    
    This endpoint:
    1. Validates the webhook payload
    2. Processes in background (non-blocking)
    3. Returns immediate response
    """
    try:
        # Parse webhook payload
        webhook_data = await request.json()
        
        # Validate webhook type
        if webhook_data.get("type") != "post_call_transcription":
            raise HTTPException(
                status_code=400,
                detail=f"Invalid webhook type: {webhook_data.get('type')}"
            )
        
        # Extract conversation ID
        conversation_id = webhook_data.get("data", {}).get("conversation_id")
        if not conversation_id:
            raise HTTPException(
                status_code=400,
                detail="Missing conversation_id in webhook data"
            )
        
        logger.info(f"Received webhook for conversation: {conversation_id}")
        
        # Process in background
        background_tasks.add_task(
            process_webhook,
            webhook_data=webhook_data,
            conversation_id=conversation_id
        )
        
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "conversation_id": conversation_id,
                "message": "Processing started in background"
            }
        )
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def process_webhook(webhook_data: Dict[str, Any], conversation_id: str):
    """
    Background task: Process webhook through pipeline.
    
    Steps:
    1. Run processing pipeline
    2. Generate Protocol + Resume
    3. Send to HOC API
    4. Log results
    """
    try:
        logger.info(f"Starting pipeline for conversation: {conversation_id}")
        
        # Import here to avoid circular imports
        from pipeline_processor import process_elevenlabs_call
        from hoc_client import send_to_hoc
        
        # Run pipeline
        result = process_elevenlabs_call(webhook_data)
        
        logger.info(f"Pipeline completed: Applicant ID {result['applicant_id']}")
        logger.info(f"  - Experiences: {result['experiences_count']}")
        logger.info(f"  - Educations: {result['educations_count']}")
        
        # Send to HOC (if configured)
        if os.getenv("HOC_API_URL"):
            try:
                hoc_response = await send_to_hoc(result)
                logger.info(f"HOC API response: {hoc_response}")
            except Exception as hoc_error:
                logger.error(f"HOC API error: {hoc_error}", exc_info=True)
        else:
            logger.warning("HOC_API_URL not configured, skipping HOC submission")
        
        logger.info(f"Processing completed for conversation: {conversation_id}")
        
    except Exception as e:
        logger.error(f"Error in background processing: {e}", exc_info=True)


@app.post("/test/pipeline")
async def test_pipeline(request: Request):
    """
    Test endpoint for manual pipeline testing.
    
    Send a webhook payload directly to test the pipeline.
    """
    try:
        webhook_data = await request.json()
        
        from pipeline_processor import process_elevenlabs_call
        
        result = process_elevenlabs_call(webhook_data)
        
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Test pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/files")
async def list_files():
    """
    Liste alle gespeicherten Output-Dateien.
    
    Returns:
        - protocols: Liste aller Protocol-Dateien
        - resumes: Liste aller Resume-Dateien
        - total_count: Gesamtanzahl der Dateien
    """
    try:
        output_dir = Path("Output")
        
        if not output_dir.exists():
            return {
                "protocols": [],
                "resumes": [],
                "total_count": 0,
                "message": "Output directory does not exist yet"
            }
        
        # Sammle alle Dateien
        protocol_files = []
        resume_files = []
        
        for file in output_dir.glob("*.json"):
            file_stat = file.stat()
            file_info = {
                "filename": file.name,
                "size_bytes": file_stat.st_size,
                "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            }
            
            if file.name.startswith("filled_protocol_"):
                # Extrahiere conversation_id
                conv_id = file.name.replace("filled_protocol_", "").replace(".json", "")
                file_info["conversation_id"] = conv_id
                protocol_files.append(file_info)
            elif file.name.startswith("resume_"):
                # Extrahiere applicant_id
                applicant_id = file.name.replace("resume_", "").replace(".json", "")
                file_info["applicant_id"] = applicant_id
                resume_files.append(file_info)
        
        # Sortiere nach Erstellungsdatum (neueste zuerst)
        protocol_files.sort(key=lambda x: x["created_at"], reverse=True)
        resume_files.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "protocols": protocol_files,
            "resumes": resume_files,
            "total_count": len(protocol_files) + len(resume_files),
            "output_directory": str(output_dir.absolute())
        }
        
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/files/{filename}")
async def get_file(filename: str):
    """
    Hole eine spezifische Output-Datei.
    
    Args:
        filename: Name der Datei (z.B. "resume_89778.json")
    
    Returns:
        JSON-Inhalt der Datei
    """
    try:
        # Sicherheit: Verhindere Directory Traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(
                status_code=400,
                detail="Invalid filename: path traversal not allowed"
            )
        
        # Nur .json Dateien erlauben
        if not filename.endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename: only .json files allowed"
            )
        
        file_path = Path("Output") / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {filename}"
            )
        
        # Lade und returniere Datei
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = json.load(f)
        
        # Füge Metadaten hinzu
        file_stat = file_path.stat()
        
        return {
            "filename": filename,
            "size_bytes": file_stat.st_size,
            "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
            "content": file_content
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON in file: {filename}"
        )
    except Exception as e:
        logger.error(f"Error reading file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/conversations")
async def list_conversations():
    """
    Liste alle verarbeiteten Conversations mit zugehörigen Dateien.
    
    Returns:
        Liste von Conversations mit Protocol + Resume
    """
    try:
        output_dir = Path("Output")
        
        if not output_dir.exists():
            return {
                "conversations": [],
                "total_count": 0
            }
        
        # Sammle alle Protocol-Dateien (diese haben conversation_id)
        conversations = []
        
        for protocol_file in output_dir.glob("filled_protocol_*.json"):
            conv_id = protocol_file.name.replace("filled_protocol_", "").replace(".json", "")
            
            # Lade Protocol um applicant_id zu extrahieren
            try:
                with open(protocol_file, 'r', encoding='utf-8') as f:
                    protocol_data = json.load(f)
                
                # Finde zugehöriges Resume (falls vorhanden)
                resume_file = None
                applicant_id = None
                
                # Suche in elevenlabs_metadata oder direkt im protocol
                if "elevenlabs_metadata" in protocol_data:
                    # Versuche applicant_id zu finden (wird nicht im protocol gespeichert)
                    pass
                
                # Suche Resume-Datei durch Timestamp-Matching
                protocol_time = protocol_file.stat().st_ctime
                for resume in output_dir.glob("resume_*.json"):
                    resume_time = resume.stat().st_ctime
                    # Wenn innerhalb von 5 Sekunden erstellt -> gehört zusammen
                    if abs(protocol_time - resume_time) < 5:
                        resume_file = resume.name
                        applicant_id = resume.name.replace("resume_", "").replace(".json", "")
                        break
                
                conversations.append({
                    "conversation_id": conv_id,
                    "applicant_id": applicant_id,
                    "protocol_file": protocol_file.name,
                    "resume_file": resume_file,
                    "created_at": datetime.fromtimestamp(protocol_time).isoformat(),
                    "metadata": protocol_data.get("elevenlabs_metadata", {})
                })
                
            except Exception as e:
                logger.warning(f"Error reading protocol {protocol_file.name}: {e}")
                continue
        
        # Sortiere nach Datum (neueste zuerst)
        conversations.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "conversations": conversations,
            "total_count": len(conversations)
        }
        
    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting webhook server on port {port}")
    
    uvicorn.run(
        "webhook_server:app",
        host="0.0.0.0",
        port=port,
        reload=False  # No reload in production
    )


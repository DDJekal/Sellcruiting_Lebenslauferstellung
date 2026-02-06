"""FastAPI Webhook Server for ElevenLabs → Processing Pipeline → HOC."""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database import (optional - only if DATABASE_URL is set)
DATABASE_ENABLED = bool(os.getenv("DATABASE_URL"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    if DATABASE_ENABLED:
        try:
            from database import DatabaseClient
            await DatabaseClient.init_tables()
            logger.info("✅ [STARTUP] Database initialized")
        except Exception as e:
            logger.error(f"❌ [STARTUP] Database initialization failed: {e}")
    else:
        logger.info("ℹ️ [STARTUP] Database not configured (DATABASE_URL not set)")
    
    yield
    
    # Shutdown
    if DATABASE_ENABLED:
        try:
            from database import DatabaseClient
            await DatabaseClient.close_pool()
            logger.info("✅ [SHUTDOWN] Database connection closed")
        except Exception as e:
            logger.error(f"❌ [SHUTDOWN] Error closing database: {e}")


# Initialize FastAPI with lifespan
app = FastAPI(
    title="KI-Sellcruiting Pipeline",
    description="ElevenLabs Webhook → Protocol Filling → Resume Generation → HOC API",
    version="1.0.0",
    lifespan=lifespan
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
            "hoc_api_configured": bool(os.getenv("HIRINGS_API_URL") and os.getenv("HIRING_API_TOKEN")),
            "database_configured": DATABASE_ENABLED,
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Check database connection if configured
    if DATABASE_ENABLED:
        try:
            from database import DatabaseClient
            pool = await DatabaseClient.get_pool()
            # Quick connection test
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health["checks"]["database_connected"] = True
        except Exception as e:
            health["checks"]["database_connected"] = False
            health["status"] = "degraded"
            health["warning"] = f"Database connection failed: {str(e)}"
    
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
    4. Log to database
    """
    try:
        logger.info(f"Starting pipeline for conversation: {conversation_id}")
        
        # Import here to avoid circular imports
        from pipeline_processor import process_elevenlabs_call
        from hoc_client import send_to_hoc
        from elevenlabs_transformer import ElevenLabsTransformer
        
        # Extract metadata for DB logging (before pipeline)
        transformer = ElevenLabsTransformer()
        elevenlabs_metadata = transformer.extract_metadata(webhook_data)
        
        # Run pipeline
        result = process_elevenlabs_call(webhook_data)
        
        logger.info(f"Pipeline completed: Applicant ID {result['applicant_id']}")
        logger.info(f"  - Experiences: {result['experiences_count']}")
        logger.info(f"  - Educations: {result['educations_count']}")
        
        # Extract qualification info
        qualification = result.get("qualification", {})
        is_qualified = qualification.get("is_qualified")
        failed_criteria = qualification.get("errors", []) if is_qualified == False else None
        
        logger.info(f"  - Qualified: {is_qualified}")
        if failed_criteria:
            logger.info(f"  - Failed criteria: {failed_criteria}")
        
        # Send to HOC (if configured)
        if os.getenv("HIRINGS_API_URL") and os.getenv("HIRING_API_TOKEN"):
            try:
                hoc_response = await send_to_hoc(result)
                logger.info(f"HOC API response: {hoc_response}")
            except Exception as hoc_error:
                logger.error(f"HOC API error: {hoc_error}", exc_info=True)
        else:
            logger.warning("HIRINGS_API_URL or HIRING_API_TOKEN not configured, skipping HOC submission")
        
        # Log to database (if configured)
        if DATABASE_ENABLED:
            try:
                from database import DatabaseClient
                await DatabaseClient.log_call(
                    conversation_id=conversation_id,
                    metadata=elevenlabs_metadata,
                    is_qualified=is_qualified,
                    failed_criteria=failed_criteria
                )
            except Exception as db_error:
                logger.error(f"Database logging error: {db_error}", exc_info=True)
        
        logger.info(f"Processing completed for conversation: {conversation_id}")
        
    except Exception as e:
        logger.error(f"Error in background processing: {e}", exc_info=True)
        
        # Still try to log failed call to database
        if DATABASE_ENABLED:
            try:
                from database import DatabaseClient
                from elevenlabs_transformer import ElevenLabsTransformer
                transformer = ElevenLabsTransformer()
                elevenlabs_metadata = transformer.extract_metadata(webhook_data)
                await DatabaseClient.log_call(
                    conversation_id=conversation_id,
                    metadata=elevenlabs_metadata,
                    is_qualified=None,  # Processing failed
                    failed_criteria=None
                )
            except Exception as db_error:
                logger.error(f"Database logging error for failed call: {db_error}")


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


# =============================================================================
# KPI ENDPOINTS
# =============================================================================

@app.get("/api/kpis/summary")
async def get_kpi_summary(campaign_id: Optional[str] = Query(None, description="Filter by campaign ID")):
    """
    Get KPI summary statistics.
    
    Returns metrics like:
    - Total calls
    - Success rate
    - Qualification rate
    - Average call duration
    - Total costs
    - Termination reasons distribution
    """
    if not DATABASE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable."
        )
    
    try:
        from database import DatabaseClient
        summary = await DatabaseClient.get_kpi_summary(campaign_id=campaign_id)
        return summary
    except Exception as e:
        logger.error(f"Error getting KPI summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kpis/calls")
async def get_calls(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    is_qualified: Optional[bool] = Query(None, description="Filter by qualification status")
):
    """
    Get list of calls with optional filters.
    
    Supports pagination via limit/offset.
    """
    if not DATABASE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable."
        )
    
    try:
        from database import DatabaseClient
        calls = await DatabaseClient.get_calls(
            limit=limit,
            offset=offset,
            campaign_id=campaign_id,
            is_qualified=is_qualified
        )
        return {
            "calls": calls,
            "count": len(calls),
            "limit": limit,
            "offset": offset,
            "filters": {
                "campaign_id": campaign_id,
                "is_qualified": is_qualified
            }
        }
    except Exception as e:
        logger.error(f"Error getting calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kpis/failed-criteria")
async def get_failed_criteria_stats(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID")
):
    """
    Get statistics on which criteria fail most often.
    
    Returns a dictionary mapping criterion names to failure counts,
    sorted by most common failures first.
    """
    if not DATABASE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable."
        )
    
    try:
        from database import DatabaseClient
        stats = await DatabaseClient.get_failed_criteria_stats(campaign_id=campaign_id)
        return {
            "failed_criteria": stats,
            "total_unique_criteria": len(stats),
            "campaign_id": campaign_id
        }
    except Exception as e:
        logger.error(f"Error getting failed criteria stats: {e}", exc_info=True)
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


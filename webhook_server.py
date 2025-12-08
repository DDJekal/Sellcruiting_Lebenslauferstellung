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


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting webhook server on port {port}")
    
    uvicorn.run(
        "webhook_server:app",
        host="0.0.0.0",
        port=port,
        reload=True  # Only for development
    )


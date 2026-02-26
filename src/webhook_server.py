"""FastAPI Webhook Server for ElevenLabs → Processing Pipeline → HOC."""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Query, Depends, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database import (optional - only if DATABASE_URL is set)
DATABASE_ENABLED = bool(os.getenv("DATABASE_URL"))

# Analytics API Key
ANALYTICS_API_KEY = os.getenv("ANALYTICS_API_KEY")

# WhatsApp Fallback
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
MIN_CALL_DURATION_FOR_PIPELINE = 120  # Calls shorter than 2 min are candidates for WhatsApp fallback

# termination_reason values that indicate the candidate was not reached.
# Extend this list as you discover new values from ElevenLabs.
WHATSAPP_TRIGGER_REASONS = {
    "no-answer",
    "busy",
    "voicemail",
    "failed",
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# API KEY AUTH
# =============================================================================

async def verify_analytics_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Verify analytics API key from X-API-Key header."""
    if not ANALYTICS_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ANALYTICS_API_KEY not configured on server"
        )
    if x_api_key != ANALYTICS_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return True


# =============================================================================
# LIFESPAN
# =============================================================================

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
    version="2.0.0",
    lifespan=lifespan
)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ki-sellcruiting-pipeline",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Lightweight health check - no DB query to avoid cold-start timeouts."""
    return {
        "status": "healthy",
        "checks": {
            "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "hoc_api_configured": bool(os.getenv("HIRINGS_API_URL") and os.getenv("HIRING_API_TOKEN")),
            "database_configured": DATABASE_ENABLED,
            "analytics_api_key": bool(ANALYTICS_API_KEY),
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# WEBHOOK ENDPOINT (unchanged pipeline)
# =============================================================================

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
    5. Run analysis (if trigger conditions met)
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
        
        # Extract transcript for potential analysis
        raw_transcript = transformer.transform(webhook_data)
        
        # =================================================================
        # FAILED-CALL DETECTION (always active, independent of WhatsApp)
        # Gescheiterte Calls (nicht erreicht, Mailbox, etc.) überspringen
        # die Pipeline – aber Metadaten werden trotzdem an HOC gesendet,
        # damit Anrufversuche für KPIs erfasst werden.
        # =================================================================
        if _is_failed_call(metadata=elevenlabs_metadata, transcript=raw_transcript):
            logger.info(
                f"[ROUTER] Call {conversation_id} als gescheitert erkannt "
                f"(nicht erreicht) – Pipeline wird übersprungen"
            )
            
            if DATABASE_ENABLED:
                try:
                    from database import DatabaseClient
                    await DatabaseClient.log_call(
                        conversation_id=conversation_id,
                        metadata=elevenlabs_metadata,
                        is_qualified=None,
                        failed_criteria=None
                    )
                except Exception as db_error:
                    logger.error(f"[ROUTER] DB logging error for failed call: {db_error}")
            
            if os.getenv("HIRINGS_API_URL") and os.getenv("HIRING_API_TOKEN"):
                try:
                    from hoc_client import send_failed_call_to_hoc
                    hoc_response = await send_failed_call_to_hoc(
                        conversation_id=conversation_id,
                        metadata=elevenlabs_metadata
                    )
                    logger.info(f"[ROUTER] HOC failed-call meta sent: {hoc_response}")
                except Exception as hoc_error:
                    logger.error(f"[ROUTER] HOC meta error for failed call: {hoc_error}", exc_info=True)
            
            if WHATSAPP_ENABLED:
                try:
                    await _maybe_trigger_whatsapp_fallback(
                        metadata=elevenlabs_metadata,
                        transcript=raw_transcript,
                        conversation_id=conversation_id
                    )
                except Exception as wa_error:
                    logger.error(f"[ROUTER] WhatsApp fallback error: {wa_error}", exc_info=True)
            
            return
        
        # Run pipeline
        result = process_elevenlabs_call(webhook_data)
        
        logger.info(f"Pipeline completed: Applicant ID {result['applicant_id']}")
        logger.info(f"  - Experiences: {result['experiences_count']}")
        logger.info(f"  - Educations: {result['educations_count']}")
        
        # Extract qualification info
        qualification = result.get("qualification", {})
        is_qualified = qualification.get("is_qualified")
        evaluation_method = qualification.get("evaluation_method", "unknown")
        failed_criteria = qualification.get("errors", []) if is_qualified == False else None
        
        # FALLBACK: Gespräch kürzer als 2 Minuten → automatisch nicht qualifiziert
        call_duration_secs = elevenlabs_metadata.get("call_duration_secs") or 0
        MIN_CALL_DURATION_SECS = 120  # 2 Minuten
        
        if call_duration_secs < MIN_CALL_DURATION_SECS and call_duration_secs > 0:
            duration_mins = round(call_duration_secs / 60, 1)
            logger.warning(f"  - Call zu kurz ({duration_mins} min < 2 min): "
                          f"KI-Qualifizierung wird abgelehnt (war: {is_qualified})")
            is_qualified = False
            evaluation_method = f"{evaluation_method}+short_call_override"
            failed_criteria = failed_criteria or []
            failed_criteria.append(f"Gespräch zu kurz ({duration_mins} min) - nicht genug Information für zuverlässige Qualifizierung")
            
            # Override auch im result-Dict, damit HOC die korrekte Info bekommt
            if "qualification" in result:
                result["qualification"]["is_qualified"] = False
                result["qualification"]["evaluation_method"] = evaluation_method
                if "errors" not in result["qualification"]:
                    result["qualification"]["errors"] = []
                result["qualification"]["errors"].append(
                    f"Gespräch zu kurz ({duration_mins} min) - automatisch nicht qualifiziert"
                )
        
        logger.info(f"  - Qualified: {is_qualified}")
        logger.info(f"  - Evaluation method: {evaluation_method}")
        
        # Safeguard: no_criteria + leeres Transkript → is_qualified = None
        if "no_criteria" in evaluation_method and is_qualified is True:
            meaningful_turns = [
                t for t in raw_transcript
                if t.get("speaker") == "A" and len(t.get("text", "")) > 5
            ]
            if len(meaningful_turns) == 0:
                logger.warning(
                    f"  - Keine Kriterien + leeres Transkript: "
                    f"is_qualified wird auf None gesetzt (statt True)"
                )
                is_qualified = None
                evaluation_method = f"{evaluation_method}+empty_transcript_override"
                if "qualification" in result:
                    result["qualification"]["is_qualified"] = None
                    result["qualification"]["evaluation_method"] = evaluation_method
            else:
                logger.info("Keine Qualifikationskriterien konfiguriert - Bewerber gilt als qualifiziert.")
        
        # Log Anerkennung-Status
        anerkennung_status = qualification.get("anerkennung_status")
        if anerkennung_status:
            logger.info(f"  - Anerkennung Status: {anerkennung_status}")
            if anerkennung_status == "nein":
                logger.warning("  - Ausländischer Abschluss OHNE deutsche Anerkennung → nicht qualifiziert")
        
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
        call_id = None
        if DATABASE_ENABLED:
            try:
                from database import DatabaseClient
                call_id = await DatabaseClient.log_call(
                    conversation_id=conversation_id,
                    metadata=elevenlabs_metadata,
                    is_qualified=is_qualified,
                    failed_criteria=failed_criteria
                )
            except Exception as db_error:
                logger.error(f"Database logging error: {db_error}", exc_info=True)
        
        # =====================================================================
        # CALL ANALYSIS (non-critical background task)
        # =====================================================================
        if DATABASE_ENABLED and call_id:
            try:
                await _maybe_run_analysis(
                    call_id=call_id,
                    transcript=raw_transcript,
                    metadata=elevenlabs_metadata
                )
            except Exception as analysis_error:
                logger.error(f"Analysis error (non-critical): {analysis_error}", exc_info=True)
        
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


async def _maybe_run_analysis(
    call_id: int,
    transcript: List[Dict[str, str]],
    metadata: Dict[str, Any]
):
    """
    Check if call qualifies for analysis, and run it.
    
    Trigger-Logik (Prioritaet):
    1. "hangup"    - Bewerber hat aufgelegt UND Call > 2 Minuten
    2. "long_call" - Call > 8 Minuten  
    3. "standard"  - Call > 5 Minuten
    
    Ergebnisse werden in separater call_analyses Tabelle gespeichert.
    """
    duration_secs = metadata.get("call_duration_secs") or 0
    termination_reason = metadata.get("termination_reason", "")
    duration_mins = duration_secs / 60
    
    trigger = None
    
    # 1. Hangup trigger: remote party ended + > 2 min (kurze Abbrecher ignorieren)
    if termination_reason == "Call ended by remote party" and duration_mins > 2:
        trigger = "hangup"
        logger.info(f"[ANALYSIS] Trigger: hangup (duration={duration_mins:.1f}min)")
    
    # 2. Long call trigger: > 8 minutes
    elif duration_mins > 8:
        trigger = "long_call"
        logger.info(f"[ANALYSIS] Trigger: long_call (duration={duration_mins:.1f}min)")
    
    # 3. Standard trigger: > 5 minutes
    elif duration_mins > 5:
        trigger = "standard"
        logger.info(f"[ANALYSIS] Trigger: standard (duration={duration_mins:.1f}min)")
    
    if not trigger:
        logger.info(f"[ANALYSIS] No trigger (duration={duration_mins:.1f}min, reason={termination_reason})")
        return
    
    # Run analysis
    from call_analyzer import CallAnalyzer
    from database import DatabaseClient
    
    analyzer = CallAnalyzer()
    analysis_result = analyzer.analyze(
        transcript=transcript,
        metadata=metadata,
        trigger=trigger
    )
    
    if analysis_result:
        analysis_id = await DatabaseClient.save_analysis(
            call_id=call_id,
            analysis=analysis_result,
            trigger=trigger
        )
        logger.info(f"[ANALYSIS] Saved to call_analyses: call_id={call_id}, analysis_id={analysis_id}")
    else:
        logger.warning(f"[ANALYSIS] Analysis returned None for call_id={call_id}")


# =============================================================================
# FAILED-CALL DETECTION
# =============================================================================

def _is_failed_call(
    metadata: Dict[str, Any],
    transcript: List[Dict[str, str]]
) -> bool:
    """
    Detect if a call failed (candidate was not reached).
    
    This check runs ALWAYS, independent of WHATSAPP_ENABLED.
    Failed calls skip the pipeline (no resume/protocol) but still send
    call metadata to HOC via /applicants/ai/call/meta for KPI tracking.
    
    Detection criteria (any one is sufficient):
    1. call_successful is explicitly not "success"
    2. termination_reason matches known failure reasons
    3. Completely empty transcript (0 turns)
    4. Very short call (< 2 min) with no meaningful applicant responses
    """
    call_successful = metadata.get("call_successful")
    call_duration_secs = metadata.get("call_duration_secs") or 0
    termination_reason = (metadata.get("termination_reason") or "").lower().strip()
    
    if call_successful and call_successful != "success":
        logger.info(f"[FAILED-CALL] call_successful={call_successful}")
        return True
    
    # Exakter Match
    if termination_reason in WHATSAPP_TRIGGER_REASONS:
        logger.info(f"[FAILED-CALL] termination_reason={termination_reason}")
        return True
    
    # Substring-Match für Varianten wie "voicemail_detection tool was called."
    if any(reason in termination_reason for reason in WHATSAPP_TRIGGER_REASONS):
        logger.info(f"[FAILED-CALL] termination_reason contains: {termination_reason}")
        return True
    
    if len(transcript) == 0:
        logger.info("[FAILED-CALL] Transkript komplett leer (0 Turns)")
        return True
    
    meaningful_turns = [
        t for t in transcript
        if t.get("speaker") == "A" and len(t.get("text", "")) > 5
    ]
    if call_duration_secs < MIN_CALL_DURATION_FOR_PIPELINE and len(meaningful_turns) == 0:
        logger.info(
            f"[FAILED-CALL] Kurzer Call ({call_duration_secs}s) ohne "
            f"aussagekräftige Bewerber-Antworten"
        )
        return True
    
    return False


# =============================================================================
# WHATSAPP FALLBACK ROUTER
# =============================================================================

async def _maybe_trigger_whatsapp_fallback(
    metadata: Dict[str, Any],
    transcript: List[Dict[str, str]],
    conversation_id: str
) -> bool:
    """
    Decide whether a failed call should trigger a WhatsApp fallback.
    
    Returns True if WhatsApp was triggered (caller should skip pipeline).
    Returns False if the call should proceed through the normal pipeline.
    
    Detection logic:
    1. call_successful is not "success"
    2. Call duration very short (< MIN_CALL_DURATION_FOR_PIPELINE) with empty/minimal transcript
    3. termination_reason matches known failure reasons
    """
    call_successful = metadata.get("call_successful")
    call_duration_secs = metadata.get("call_duration_secs") or 0
    termination_reason = (metadata.get("termination_reason") or "").lower().strip()
    to_number = metadata.get("to_number")
    applicant_id = metadata.get("applicant_id")
    
    # Need minimum data to trigger WhatsApp
    if not to_number or not applicant_id:
        logger.info(f"[ROUTER] No to_number or applicant_id, cannot trigger WhatsApp")
        return False
    
    trigger_reason = None
    
    # Check 1: Explicit failure status from ElevenLabs
    if call_successful and call_successful != "success":
        trigger_reason = "call_not_successful"
    
    # Check 2: Known termination reasons indicating unreachable
    if not trigger_reason and termination_reason in WHATSAPP_TRIGGER_REASONS:
        trigger_reason = termination_reason
    
    # Check 3: Very short call with no meaningful transcript
    # (short_call_override already catches this for qualification,
    #  but for WhatsApp we also want to check transcript emptiness)
    if not trigger_reason:
        meaningful_turns = [t for t in transcript if t.get("speaker") == "A" and len(t.get("text", "")) > 5]
        if call_duration_secs < MIN_CALL_DURATION_FOR_PIPELINE and len(meaningful_turns) == 0:
            if call_duration_secs > 0:
                trigger_reason = "short_call_no_response"
    
    if not trigger_reason:
        return False
    
    logger.info(
        f"[ROUTER] Call {conversation_id} detected as failed: "
        f"reason={trigger_reason}, duration={call_duration_secs}s, "
        f"termination={termination_reason}, successful={call_successful}"
    )
    
    # Log the failed call to DB before triggering WhatsApp
    if DATABASE_ENABLED:
        try:
            from database import DatabaseClient
            await DatabaseClient.log_call(
                conversation_id=conversation_id,
                metadata=metadata,
                is_qualified=None,
                failed_criteria=None
            )
        except Exception as db_error:
            logger.error(f"[ROUTER] DB logging error for failed call: {db_error}")
    
    # Trigger WhatsApp fallback
    try:
        from whatsapp_handler import WhatsAppHandler
        handler = WhatsAppHandler()
        session_id = await handler.trigger_fallback(
            metadata=metadata,
            trigger_reason=trigger_reason
        )
        
        if session_id:
            logger.info(f"[ROUTER] WhatsApp fallback triggered: session_id={session_id}")
            return True
        else:
            logger.error(f"[ROUTER] WhatsApp fallback failed for {conversation_id}")
            return False
            
    except Exception as e:
        logger.error(f"[ROUTER] Error triggering WhatsApp fallback: {e}", exc_info=True)
        return False


# =============================================================================
# WHATSAPP WEBHOOK ENDPOINT
# =============================================================================

@app.post("/whatsapp/webhook")
async def whatsapp_incoming_webhook(request: Request):
    """
    Receive incoming WhatsApp messages from Twilio.
    
    Twilio sends POST with application/x-www-form-urlencoded, not JSON.
    Key fields: From, Body, MessageSid, To, NumMedia
    
    Returns empty TwiML response (Twilio expects this).
    """
    try:
        # Parse form data (Twilio sends URL-encoded, not JSON)
        form_data = await request.form()
        params = dict(form_data)
        
        from_number = params.get("From", "")
        message_body = params.get("Body", "").strip()
        message_sid = params.get("MessageSid", "")
        
        if not from_number or not message_body:
            logger.warning(f"[WHATSAPP-WH] Empty message or missing From: {params}")
            return _twiml_empty_response()
        
        logger.info(f"[WHATSAPP-WH] Incoming: from={from_number}, sid={message_sid}, body={message_body[:80]}...")
        
        # Validate Twilio signature (security)
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        if twilio_signature:
            from twilio_client import TwilioWhatsAppClient
            twilio = TwilioWhatsAppClient()
            webhook_url = str(request.url)
            if not twilio.validate_webhook_signature(webhook_url, params, twilio_signature):
                logger.warning(f"[WHATSAPP-WH] Invalid Twilio signature from {from_number}")
                raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Strip "whatsapp:" prefix for DB lookup
        clean_number = from_number.replace("whatsapp:", "")
        
        if not DATABASE_ENABLED:
            logger.warning("[WHATSAPP-WH] Database not enabled, cannot process WhatsApp messages")
            return _twiml_empty_response()
        
        # Find active session for this number
        from database import DatabaseClient
        session = await DatabaseClient.get_active_whatsapp_session(clean_number)
        
        if not session:
            # Also try with whatsapp: prefix
            session = await DatabaseClient.get_active_whatsapp_session(from_number)
        
        if not session:
            logger.info(f"[WHATSAPP-WH] No active session for {from_number}, ignoring message")
            return _twiml_empty_response()
        
        # Handle the incoming message
        from whatsapp_handler import WhatsAppHandler
        handler = WhatsAppHandler()
        await handler.handle_incoming_message(
            session=session,
            message_body=message_body,
            from_number=from_number
        )
        
        return _twiml_empty_response()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WHATSAPP-WH] Error processing incoming message: {e}", exc_info=True)
        return _twiml_empty_response()


def _twiml_empty_response():
    """Return an empty TwiML response (Twilio expects XML)."""
    from fastapi.responses import Response
    return Response(
        content="<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
        media_type="application/xml"
    )


# =============================================================================
# TEST / DEBUG ENDPOINTS
# =============================================================================

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


@app.post("/test/analyze")
async def test_analyze(request: Request):
    """
    Test endpoint for call analysis.
    
    Expects JSON with:
    - transcript: list of {"speaker": "A"|"B", "text": "..."}
    - metadata: dict with call_duration_secs, termination_reason, etc.
    - trigger: "hangup" or "long_call" (optional, default "hangup")
    """
    try:
        data = await request.json()
        
        transcript = data.get("transcript", [])
        metadata = data.get("metadata", {})
        trigger = data.get("trigger", "hangup")
        
        if not transcript:
            raise HTTPException(status_code=400, detail="Missing transcript")
        
        from call_analyzer import CallAnalyzer
        
        analyzer = CallAnalyzer()
        result = analyzer.analyze(
            transcript=transcript,
            metadata=metadata,
            trigger=trigger
        )
        
        if result is None:
            raise HTTPException(status_code=500, detail="Analysis returned None")
        
        return {
            "status": "success",
            "trigger": trigger,
            "analysis": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test analyze error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/files")
async def list_files():
    """Liste alle gespeicherten Output-Dateien."""
    try:
        output_dir = Path("Output")
        
        if not output_dir.exists():
            return {
                "protocols": [],
                "resumes": [],
                "total_count": 0,
                "message": "Output directory does not exist yet"
            }
        
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
            
            if file.name.startswith("filled_protocol_") or file.name.startswith("protocol_"):
                conv_id = file.name.replace("filled_protocol_", "").replace("protocol_", "").replace(".json", "")
                file_info["conversation_id"] = conv_id
                protocol_files.append(file_info)
            elif file.name.startswith("resume_"):
                applicant_id = file.name.replace("resume_", "").replace(".json", "")
                file_info["applicant_id"] = applicant_id
                resume_files.append(file_info)
        
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
    """Hole eine spezifische Output-Datei."""
    try:
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(
                status_code=400,
                detail="Invalid filename: path traversal not allowed"
            )
        
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
        
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = json.load(f)
        
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
    """Liste alle verarbeiteten Conversations mit zugehörigen Dateien."""
    try:
        output_dir = Path("Output")
        
        if not output_dir.exists():
            return {
                "conversations": [],
                "total_count": 0
            }
        
        conversations = []
        
        for protocol_file in list(output_dir.glob("filled_protocol_*.json")) + list(output_dir.glob("protocol_*.json")):
            conv_id = protocol_file.name.replace("filled_protocol_", "").replace("protocol_", "").replace(".json", "")
            
            try:
                with open(protocol_file, 'r', encoding='utf-8') as f:
                    protocol_data = json.load(f)
                
                resume_file = None
                applicant_id = None
                
                protocol_time = protocol_file.stat().st_ctime
                for resume in output_dir.glob("resume_*.json"):
                    resume_time = resume.stat().st_ctime
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
        
        conversations.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "conversations": conversations,
            "total_count": len(conversations)
        }
        
    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# KPI ENDPOINTS (API-Key protected)
# =============================================================================

@app.get("/api/kpis/summary")
async def get_kpi_summary(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get KPI summary statistics."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
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
    is_qualified: Optional[bool] = Query(None, description="Filter by qualification status"),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get list of calls with optional filters."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
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
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get statistics on which criteria fail most often."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
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


# =============================================================================
# ANALYSIS ENDPOINTS (API-Key protected)
# =============================================================================

@app.get("/api/analysis/summary")
async def get_analysis_summary(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get aggregated analysis KPIs."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    try:
        from database import DatabaseClient
        summary = await DatabaseClient.get_analysis_summary(campaign_id=campaign_id)
        return summary
    except Exception as e:
        logger.error(f"Error getting analysis summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/hangups")
async def get_hangup_analyses(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get all hangup call analyses."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    try:
        from database import DatabaseClient
        analyses = await DatabaseClient.get_hangup_analyses(limit=limit, offset=offset)
        return {
            "analyses": analyses,
            "count": len(analyses),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error getting hangup analyses: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/all")
async def get_all_analyses(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    trigger_type: Optional[str] = Query(None, description="Filter by trigger type: hangup, standard, long_call"),
    _auth: bool = Depends(verify_analytics_key)
):
    """Get all call analyses with optional trigger filter."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    try:
        from database import DatabaseClient
        analyses = await DatabaseClient.get_analyses(
            limit=limit, offset=offset, trigger_type=trigger_type
        )
        return {
            "analyses": analyses,
            "count": len(analyses),
            "limit": limit,
            "offset": offset,
            "trigger_type": trigger_type
        }
    except Exception as e:
        logger.error(f"Error getting analyses: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/conversation/{conversation_id}")
async def get_analysis_by_conversation(
    conversation_id: str,
    _auth: bool = Depends(verify_analytics_key)
):
    """Get analysis for a specific conversation."""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    try:
        from database import DatabaseClient
        analysis = await DatabaseClient.get_analysis_by_conversation(conversation_id)
        if not analysis:
            raise HTTPException(status_code=404, detail=f"No data found for conversation {conversation_id}")
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MAIN
# =============================================================================

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

"""Database client for call tracking, KPIs, and call analysis."""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Async PostgreSQL client for call tracking and analysis."""
    
    _pool: Optional[asyncpg.Pool] = None
    
    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Get or create connection pool."""
        if cls._pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not set")
            
            cls._pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5
            )
            logger.info("✅ [DATABASE] Connection pool created")
        
        return cls._pool
    
    @classmethod
    async def close_pool(cls):
        """Close connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("✅ [DATABASE] Connection pool closed")
    
    @classmethod
    async def init_tables(cls):
        """
        Initialize database tables with automatic migration.
        
        Detects old table structure (missing analysis_trigger column)
        and migrates by dropping and recreating.
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # Check if table exists at all
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'calls'
                )
            """)
            
            if table_exists:
                # Check if it's the old structure (no analysis_trigger column)
                has_analysis = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'calls'
                        AND column_name = 'analysis_trigger'
                    )
                """)
                
                if not has_analysis:
                    logger.info("⚠️ [DATABASE] Alte Tabellenstruktur erkannt, migriere...")
                    await conn.execute("DROP TABLE IF EXISTS calls CASCADE;")
                    logger.info("✅ [DATABASE] Alte Tabelle entfernt")
            
            # Create new table (IF NOT EXISTS = safe on restart)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id                      SERIAL PRIMARY KEY,
                    conversation_id         VARCHAR(255) UNIQUE NOT NULL,
                    campaign_id             VARCHAR(255),
                    company_name            VARCHAR(255),
                    campaign_role_title     VARCHAR(255),
                    
                    -- Call-Metriken
                    call_duration_minutes   DECIMAL(10, 2),
                    termination_reason      VARCHAR(100),
                    call_successful         BOOLEAN,
                    
                    -- Qualifikation
                    is_qualified            BOOLEAN,
                    failed_criteria         TEXT,
                    
                    -- Timestamps
                    call_timestamp          TIMESTAMP,
                    processed_at            TIMESTAMP DEFAULT NOW(),
                    
                    -- ====== ANALYSE-FELDER (NULL wenn nicht analysiert) ======
                    
                    analysis_trigger        VARCHAR(20),
                    quality_score           INTEGER,
                    
                    -- Phasen
                    hangup_phase            INTEGER,
                    hangup_phase_name       VARCHAR(100),
                    last_completed_phase    INTEGER,
                    phases_completed        TEXT,
                    phases_missing          TEXT,
                    
                    -- Abbruch
                    hangup_reason           TEXT,
                    hangup_trigger_moment   TEXT,
                    hangup_category         VARCHAR(50),
                    hangup_severity         INTEGER,
                    
                    -- Sentiment
                    sentiment_flow          TEXT,
                    sentiment_trend         VARCHAR(20),
                    sentiment_turning_point INTEGER,
                    
                    -- Engagement
                    engagement_score        INTEGER,
                    avg_response_length     VARCHAR(20),
                    signs_of_disinterest    TEXT,
                    signs_of_confusion      TEXT,
                    
                    -- Agent-Fehler
                    agent_errors            TEXT,
                    error_count             INTEGER,
                    top_error_category      VARCHAR(50),
                    
                    -- Regelverstoesse
                    rule_violations         TEXT,
                    rule_violation_count    INTEGER,
                    
                    -- Informationsqualitaet
                    completeness_score      INTEGER,
                    questions_asked         INTEGER,
                    questions_expected      INTEGER,
                    missing_topics          TEXT,
                    vague_answers           TEXT,
                    
                    -- Zusammenfassung
                    analysis_summary        TEXT,
                    improvement_suggestions TEXT,
                    analyzed_at             TIMESTAMP
                );
                
                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_calls_campaign_id ON calls(campaign_id);
                CREATE INDEX IF NOT EXISTS idx_calls_call_timestamp ON calls(call_timestamp);
                CREATE INDEX IF NOT EXISTS idx_calls_is_qualified ON calls(is_qualified);
                CREATE INDEX IF NOT EXISTS idx_calls_analysis_trigger ON calls(analysis_trigger);
                CREATE INDEX IF NOT EXISTS idx_calls_termination_reason ON calls(termination_reason);
            """)
            
            logger.info("✅ [DATABASE] Tables initialized")
    
    # =========================================================================
    # CALL LOGGING
    # =========================================================================
    
    @classmethod
    async def log_call(
        cls,
        conversation_id: str,
        metadata: Dict[str, Any],
        is_qualified: Optional[bool] = None,
        failed_criteria: Optional[List[str]] = None
    ) -> int:
        """
        Log a call to the database.
        
        Returns:
            ID of the inserted row (needed for update_analysis)
        """
        pool = await cls.get_pool()
        
        # Convert duration from seconds to minutes
        duration_secs = metadata.get("call_duration_secs")
        duration_minutes = None
        if duration_secs is not None:
            duration_minutes = round(duration_secs / 60, 2)
        
        # Convert unix timestamp to datetime
        call_timestamp = None
        start_time_unix = metadata.get("start_time_unix_secs")
        if start_time_unix:
            call_timestamp = datetime.fromtimestamp(start_time_unix)
        
        # Format failed criteria
        failed_criteria_str = None
        if is_qualified == False and failed_criteria:
            failed_criteria_str = ", ".join(failed_criteria)
        
        async with pool.acquire() as conn:
            row_id = await conn.fetchval("""
                INSERT INTO calls (
                    conversation_id,
                    campaign_id,
                    company_name,
                    campaign_role_title,
                    call_duration_minutes,
                    termination_reason,
                    call_successful,
                    is_qualified,
                    failed_criteria,
                    call_timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    is_qualified = EXCLUDED.is_qualified,
                    failed_criteria = EXCLUDED.failed_criteria,
                    processed_at = NOW()
                RETURNING id
            """,
                conversation_id,
                metadata.get("campaign_id"),
                metadata.get("company_name"),
                metadata.get("campaign_role_title"),
                duration_minutes,
                metadata.get("termination_reason"),
                metadata.get("call_successful") == "success" if metadata.get("call_successful") else None,
                is_qualified,
                failed_criteria_str,
                call_timestamp
            )
            
            logger.info(f"✅ [DATABASE] Call logged: {conversation_id} (id={row_id})")
            return row_id
    
    # =========================================================================
    # ANALYSIS UPDATE
    # =========================================================================
    
    @classmethod
    async def update_analysis(
        cls,
        call_id: int,
        analysis: Dict[str, Any],
        trigger: str = "hangup"
    ):
        """
        Update a call record with analysis results.
        
        Args:
            call_id: ID of the call record
            analysis: Analysis result dict from CallAnalyzer
            trigger: "hangup" or "long_call"
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE calls SET
                    analysis_trigger = $1,
                    quality_score = $2,
                    hangup_phase = $3,
                    hangup_phase_name = $4,
                    last_completed_phase = $5,
                    phases_completed = $6,
                    phases_missing = $7,
                    hangup_reason = $8,
                    hangup_trigger_moment = $9,
                    hangup_category = $10,
                    hangup_severity = $11,
                    sentiment_flow = $12,
                    sentiment_trend = $13,
                    sentiment_turning_point = $14,
                    engagement_score = $15,
                    avg_response_length = $16,
                    signs_of_disinterest = $17,
                    signs_of_confusion = $18,
                    agent_errors = $19,
                    error_count = $20,
                    top_error_category = $21,
                    rule_violations = $22,
                    rule_violation_count = $23,
                    completeness_score = $24,
                    questions_asked = $25,
                    questions_expected = $26,
                    missing_topics = $27,
                    vague_answers = $28,
                    analysis_summary = $29,
                    improvement_suggestions = $30,
                    analyzed_at = NOW()
                WHERE id = $31
            """,
                trigger,
                analysis.get("quality_score"),
                analysis.get("hangup_phase"),
                analysis.get("hangup_phase_name"),
                analysis.get("last_completed_phase"),
                analysis.get("phases_completed"),
                analysis.get("phases_missing"),
                analysis.get("hangup_reason"),
                analysis.get("hangup_trigger_moment"),
                analysis.get("hangup_category"),
                analysis.get("hangup_severity"),
                analysis.get("sentiment_flow"),
                analysis.get("sentiment_trend"),
                analysis.get("sentiment_turning_point"),
                analysis.get("engagement_score"),
                analysis.get("avg_response_length"),
                analysis.get("signs_of_disinterest"),
                analysis.get("signs_of_confusion"),
                analysis.get("agent_errors"),
                analysis.get("error_count"),
                analysis.get("top_error_category"),
                analysis.get("rule_violations"),
                analysis.get("rule_violation_count"),
                analysis.get("completeness_score"),
                analysis.get("questions_asked"),
                analysis.get("questions_expected"),
                analysis.get("missing_topics"),
                analysis.get("vague_answers"),
                analysis.get("analysis_summary"),
                analysis.get("improvement_suggestions"),
                call_id
            )
            
            logger.info(f"✅ [DATABASE] Analysis saved for call_id={call_id} (trigger={trigger})")
    
    # =========================================================================
    # KPI QUERIES
    # =========================================================================
    
    @classmethod
    async def get_kpi_summary(cls, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """Get KPI summary statistics."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            where_clause = ""
            params = []
            if campaign_id:
                where_clause = "WHERE campaign_id = $1"
                params = [campaign_id]
            
            and_or_where = "AND" if where_clause else "WHERE"
            
            total_calls = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause}", *params
            )
            
            successful_calls = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {and_or_where} call_successful = true", *params
            )
            
            qualified_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {and_or_where} is_qualified = true", *params
            )
            
            not_qualified_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {and_or_where} is_qualified = false", *params
            )
            
            avg_duration = await conn.fetchval(
                f"SELECT AVG(call_duration_minutes) FROM calls {where_clause} {and_or_where} call_duration_minutes IS NOT NULL", *params
            )
            
            analyzed_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {and_or_where} analysis_trigger IS NOT NULL", *params
            )
            
            avg_quality = await conn.fetchval(
                f"SELECT AVG(quality_score) FROM calls {where_clause} {and_or_where} quality_score IS NOT NULL", *params
            )
            
            termination_reasons = await conn.fetch(
                f"""SELECT termination_reason, COUNT(*) as count 
                    FROM calls {where_clause} 
                    {and_or_where} termination_reason IS NOT NULL
                    GROUP BY termination_reason""", *params
            )
            
            return {
                "total_calls": total_calls or 0,
                "successful_calls": successful_calls or 0,
                "success_rate": round((successful_calls or 0) / total_calls * 100, 1) if total_calls else 0,
                "qualified_candidates": qualified_count or 0,
                "not_qualified_candidates": not_qualified_count or 0,
                "qualification_rate": round((qualified_count or 0) / total_calls * 100, 1) if total_calls else 0,
                "avg_call_duration_minutes": round(float(avg_duration), 2) if avg_duration else 0,
                "analyzed_calls": analyzed_count or 0,
                "avg_quality_score": round(float(avg_quality), 1) if avg_quality else None,
                "termination_reasons": {row["termination_reason"]: row["count"] for row in termination_reasons},
                "campaign_id": campaign_id
            }
    
    @classmethod
    async def get_calls(
        cls,
        limit: int = 50,
        offset: int = 0,
        campaign_id: Optional[str] = None,
        is_qualified: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Get list of calls with optional filters."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            conditions = []
            params = []
            param_idx = 1
            
            if campaign_id:
                conditions.append(f"campaign_id = ${param_idx}")
                params.append(campaign_id)
                param_idx += 1
            
            if is_qualified is not None:
                conditions.append(f"is_qualified = ${param_idx}")
                params.append(is_qualified)
                param_idx += 1
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.extend([limit, offset])
            
            rows = await conn.fetch(
                f"""SELECT * FROM calls 
                    {where_clause}
                    ORDER BY call_timestamp DESC NULLS LAST
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
                *params
            )
            
            return [dict(row) for row in rows]
    
    @classmethod
    async def get_failed_criteria_stats(cls, campaign_id: Optional[str] = None) -> Dict[str, int]:
        """Get statistics on which criteria fail most often."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            where_clause = ""
            params = []
            if campaign_id:
                where_clause = "AND campaign_id = $1"
                params = [campaign_id]
            
            rows = await conn.fetch(
                f"""SELECT failed_criteria FROM calls 
                    WHERE is_qualified = false 
                    AND failed_criteria IS NOT NULL
                    {where_clause}""", *params
            )
            
            criteria_counts: Dict[str, int] = {}
            for row in rows:
                if row["failed_criteria"]:
                    for criterion in row["failed_criteria"].split(", "):
                        criterion = criterion.strip()
                        if criterion:
                            criteria_counts[criterion] = criteria_counts.get(criterion, 0) + 1
            
            return dict(sorted(criteria_counts.items(), key=lambda x: x[1], reverse=True))
    
    # =========================================================================
    # ANALYSIS QUERIES
    # =========================================================================
    
    @classmethod
    async def get_analysis_summary(cls, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """Get aggregated analysis KPIs."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            where_base = "WHERE analysis_trigger IS NOT NULL"
            params = []
            if campaign_id:
                where_base += " AND campaign_id = $1"
                params = [campaign_id]
            
            total_analyzed = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_base}", *params
            )
            
            avg_quality = await conn.fetchval(
                f"SELECT AVG(quality_score) FROM calls {where_base}", *params
            )
            
            avg_engagement = await conn.fetchval(
                f"SELECT AVG(engagement_score) FROM calls {where_base}", *params
            )
            
            avg_completeness = await conn.fetchval(
                f"SELECT AVG(completeness_score) FROM calls {where_base}", *params
            )
            
            # Top error categories
            error_cats = await conn.fetch(
                f"""SELECT top_error_category, COUNT(*) as count 
                    FROM calls {where_base} AND top_error_category IS NOT NULL
                    GROUP BY top_error_category ORDER BY count DESC""", *params
            )
            
            # Hangup phases distribution
            hangup_phases = await conn.fetch(
                f"""SELECT hangup_phase, hangup_phase_name, COUNT(*) as count 
                    FROM calls {where_base} AND hangup_phase IS NOT NULL
                    GROUP BY hangup_phase, hangup_phase_name ORDER BY count DESC""", *params
            )
            
            # Sentiment trends
            sentiment_trends = await conn.fetch(
                f"""SELECT sentiment_trend, COUNT(*) as count 
                    FROM calls {where_base} AND sentiment_trend IS NOT NULL
                    GROUP BY sentiment_trend ORDER BY count DESC""", *params
            )
            
            # Hangup vs long_call
            trigger_dist = await conn.fetch(
                f"""SELECT analysis_trigger, COUNT(*) as count 
                    FROM calls {where_base}
                    GROUP BY analysis_trigger""", *params
            )
            
            return {
                "total_analyzed": total_analyzed or 0,
                "avg_quality_score": round(float(avg_quality), 1) if avg_quality else None,
                "avg_engagement_score": round(float(avg_engagement), 1) if avg_engagement else None,
                "avg_completeness_score": round(float(avg_completeness), 1) if avg_completeness else None,
                "top_error_categories": {row["top_error_category"]: row["count"] for row in error_cats},
                "hangup_phases": {row["hangup_phase_name"]: row["count"] for row in hangup_phases if row["hangup_phase_name"]},
                "sentiment_trends": {row["sentiment_trend"]: row["count"] for row in sentiment_trends},
                "trigger_distribution": {row["analysis_trigger"]: row["count"] for row in trigger_dist},
                "campaign_id": campaign_id
            }
    
    @classmethod
    async def get_hangup_analyses(
        cls, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all hangup analyses."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM calls 
                    WHERE analysis_trigger = 'hangup'
                    ORDER BY analyzed_at DESC NULLS LAST
                    LIMIT $1 OFFSET $2""",
                limit, offset
            )
            return [dict(row) for row in rows]
    
    @classmethod
    async def get_analysis_by_conversation(cls, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis for a specific conversation."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM calls WHERE conversation_id = $1",
                conversation_id
            )
            return dict(row) if row else None

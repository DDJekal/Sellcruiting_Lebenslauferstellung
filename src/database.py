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
        
        Structure:
        - calls: Call-Metriken + Qualifikation (schlank)
        - call_analyses: Separate Analyse-Ergebnisse (FK -> calls)
        
        Migration: Detects old structure (analysis_trigger in calls)
        and migrates by dropping and recreating both tables.
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # Check if calls table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'calls'
                )
            """)
            
            if table_exists:
                # Check if it's the old structure (analysis_trigger in calls = old monolithic table)
                has_analysis_in_calls = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'calls'
                        AND column_name = 'analysis_trigger'
                    )
                """)
                
                if has_analysis_in_calls:
                    logger.info("[DATABASE] Alte monolithische Tabellenstruktur erkannt, migriere zu 2-Table-Struktur...")
                    await conn.execute("DROP TABLE IF EXISTS call_analyses CASCADE;")
                    await conn.execute("DROP TABLE IF EXISTS calls CASCADE;")
                    logger.info("[DATABASE] Alte Tabellen entfernt")
            
            # ============================================================
            # TABLE 1: calls (schlank - nur Call-Metriken + Qualifikation)
            # ============================================================
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
                    processed_at            TIMESTAMP DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_calls_campaign_id ON calls(campaign_id);
                CREATE INDEX IF NOT EXISTS idx_calls_call_timestamp ON calls(call_timestamp);
                CREATE INDEX IF NOT EXISTS idx_calls_is_qualified ON calls(is_qualified);
                CREATE INDEX IF NOT EXISTS idx_calls_termination_reason ON calls(termination_reason);
            """)
            
            # ============================================================
            # TABLE 2: call_analyses (Analyse-Ergebnisse, FK -> calls)
            # ============================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS call_analyses (
                    id                      SERIAL PRIMARY KEY,
                    call_id                 INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
                    
                    -- Trigger & Score
                    trigger_type            VARCHAR(20) NOT NULL,
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
                    analyzed_at             TIMESTAMP DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_analyses_call_id ON call_analyses(call_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_trigger ON call_analyses(trigger_type);
                CREATE INDEX IF NOT EXISTS idx_analyses_quality ON call_analyses(quality_score);
            """)
            
            logger.info("[DATABASE] Tables initialized (calls + call_analyses)")
    
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
    async def save_analysis(
        cls,
        call_id: int,
        analysis: Dict[str, Any],
        trigger: str = "standard"
    ) -> int:
        """
        Save analysis results to call_analyses table.
        
        Args:
            call_id: ID of the call record (FK -> calls)
            analysis: Analysis result dict from CallAnalyzer
            trigger: "hangup", "standard", or "long_call"
            
        Returns:
            ID of the inserted analysis row
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            row_id = await conn.fetchval("""
                INSERT INTO call_analyses (
                    call_id, trigger_type, quality_score,
                    hangup_phase, hangup_phase_name, last_completed_phase,
                    phases_completed, phases_missing,
                    hangup_reason, hangup_trigger_moment, hangup_category, hangup_severity,
                    sentiment_flow, sentiment_trend, sentiment_turning_point,
                    engagement_score, avg_response_length, signs_of_disinterest, signs_of_confusion,
                    agent_errors, error_count, top_error_category,
                    rule_violations, rule_violation_count,
                    completeness_score, questions_asked, questions_expected,
                    missing_topics, vague_answers,
                    analysis_summary, improvement_suggestions
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                    $21, $22, $23, $24, $25, $26, $27, $28, $29, $30
                )
                RETURNING id
            """,
                call_id,
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
                analysis.get("improvement_suggestions")
            )
            
            logger.info(f"[DATABASE] Analysis saved: call_id={call_id}, analysis_id={row_id}, trigger={trigger}")
            return row_id
    
    # =========================================================================
    # KPI QUERIES
    # =========================================================================
    
    @classmethod
    async def get_kpi_summary(cls, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """Get KPI summary statistics (calls + analysis overview)."""
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
            
            # Analysis counts from call_analyses table (via JOIN)
            if campaign_id:
                analyzed_count = await conn.fetchval(
                    """SELECT COUNT(DISTINCT ca.call_id) FROM call_analyses ca
                       JOIN calls c ON ca.call_id = c.id
                       WHERE c.campaign_id = $1""", campaign_id
                )
                avg_quality = await conn.fetchval(
                    """SELECT AVG(ca.quality_score) FROM call_analyses ca
                       JOIN calls c ON ca.call_id = c.id
                       WHERE c.campaign_id = $1 AND ca.quality_score IS NOT NULL""", campaign_id
                )
            else:
                analyzed_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM call_analyses"
                )
                avg_quality = await conn.fetchval(
                    "SELECT AVG(quality_score) FROM call_analyses WHERE quality_score IS NOT NULL"
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
        """Get aggregated analysis KPIs from call_analyses table."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # Base: always query call_analyses, optionally JOIN for campaign filter
            if campaign_id:
                base_from = "call_analyses ca JOIN calls c ON ca.call_id = c.id"
                where_base = "WHERE c.campaign_id = $1"
                params = [campaign_id]
            else:
                base_from = "call_analyses ca"
                where_base = ""
                params = []
            
            and_or_where = "AND" if where_base else "WHERE"
            
            total_analyzed = await conn.fetchval(
                f"SELECT COUNT(*) FROM {base_from} {where_base}", *params
            )
            
            avg_quality = await conn.fetchval(
                f"SELECT AVG(ca.quality_score) FROM {base_from} {where_base}", *params
            )
            
            avg_engagement = await conn.fetchval(
                f"SELECT AVG(ca.engagement_score) FROM {base_from} {where_base}", *params
            )
            
            avg_completeness = await conn.fetchval(
                f"SELECT AVG(ca.completeness_score) FROM {base_from} {where_base}", *params
            )
            
            # Top error categories
            error_cats = await conn.fetch(
                f"""SELECT ca.top_error_category, COUNT(*) as count 
                    FROM {base_from} {where_base} {and_or_where} ca.top_error_category IS NOT NULL
                    GROUP BY ca.top_error_category ORDER BY count DESC""", *params
            )
            
            # Hangup phases distribution
            hangup_phases = await conn.fetch(
                f"""SELECT ca.hangup_phase, ca.hangup_phase_name, COUNT(*) as count 
                    FROM {base_from} {where_base} {and_or_where} ca.hangup_phase IS NOT NULL
                    GROUP BY ca.hangup_phase, ca.hangup_phase_name ORDER BY count DESC""", *params
            )
            
            # Sentiment trends
            sentiment_trends = await conn.fetch(
                f"""SELECT ca.sentiment_trend, COUNT(*) as count 
                    FROM {base_from} {where_base} {and_or_where} ca.sentiment_trend IS NOT NULL
                    GROUP BY ca.sentiment_trend ORDER BY count DESC""", *params
            )
            
            # Trigger distribution (hangup / standard / long_call)
            trigger_dist = await conn.fetch(
                f"""SELECT ca.trigger_type, COUNT(*) as count 
                    FROM {base_from} {where_base}
                    GROUP BY ca.trigger_type""", *params
            )
            
            return {
                "total_analyzed": total_analyzed or 0,
                "avg_quality_score": round(float(avg_quality), 1) if avg_quality else None,
                "avg_engagement_score": round(float(avg_engagement), 1) if avg_engagement else None,
                "avg_completeness_score": round(float(avg_completeness), 1) if avg_completeness else None,
                "top_error_categories": {row["top_error_category"]: row["count"] for row in error_cats},
                "hangup_phases": {row["hangup_phase_name"]: row["count"] for row in hangup_phases if row["hangup_phase_name"]},
                "sentiment_trends": {row["sentiment_trend"]: row["count"] for row in sentiment_trends},
                "trigger_distribution": {row["trigger_type"]: row["count"] for row in trigger_dist},
                "campaign_id": campaign_id
            }
    
    @classmethod
    async def get_hangup_analyses(
        cls, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all hangup analyses (JOIN with calls for context)."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.conversation_id, c.campaign_id, c.company_name,
                          c.campaign_role_title, c.call_duration_minutes,
                          c.termination_reason, c.is_qualified,
                          ca.*
                   FROM call_analyses ca
                   JOIN calls c ON ca.call_id = c.id
                   WHERE ca.trigger_type = 'hangup'
                   ORDER BY ca.analyzed_at DESC NULLS LAST
                   LIMIT $1 OFFSET $2""",
                limit, offset
            )
            return [dict(row) for row in rows]
    
    @classmethod
    async def get_analysis_by_conversation(cls, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis for a specific conversation (JOIN with calls)."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT c.conversation_id, c.campaign_id, c.company_name,
                          c.campaign_role_title, c.call_duration_minutes,
                          c.termination_reason, c.is_qualified,
                          ca.*
                   FROM call_analyses ca
                   JOIN calls c ON ca.call_id = c.id
                   WHERE c.conversation_id = $1
                   ORDER BY ca.analyzed_at DESC
                   LIMIT 1""",
                conversation_id
            )
            return dict(row) if row else None
    
    @classmethod
    async def get_analyses(
        cls, limit: int = 50, offset: int = 0,
        trigger_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all analyses with optional trigger filter."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            if trigger_type:
                rows = await conn.fetch(
                    """SELECT c.conversation_id, c.campaign_id, c.company_name,
                              c.campaign_role_title, c.call_duration_minutes,
                              c.termination_reason, c.is_qualified,
                              ca.*
                       FROM call_analyses ca
                       JOIN calls c ON ca.call_id = c.id
                       WHERE ca.trigger_type = $1
                       ORDER BY ca.analyzed_at DESC NULLS LAST
                       LIMIT $2 OFFSET $3""",
                    trigger_type, limit, offset
                )
            else:
                rows = await conn.fetch(
                    """SELECT c.conversation_id, c.campaign_id, c.company_name,
                              c.campaign_role_title, c.call_duration_minutes,
                              c.termination_reason, c.is_qualified,
                              ca.*
                       FROM call_analyses ca
                       JOIN calls c ON ca.call_id = c.id
                       ORDER BY ca.analyzed_at DESC NULLS LAST
                       LIMIT $1 OFFSET $2""",
                    limit, offset
                )
            return [dict(row) for row in rows]

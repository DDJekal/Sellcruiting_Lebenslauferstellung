"""Database client for call tracking and KPI logging."""
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Async PostgreSQL client for call tracking."""
    
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
        """Initialize database tables if they don't exist."""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id                      SERIAL PRIMARY KEY,
                    conversation_id         VARCHAR(255) UNIQUE NOT NULL,
                    campaign_id             VARCHAR(255),
                    agent_id                VARCHAR(255),
                    
                    -- Kandidaten-Info
                    candidate_first_name    VARCHAR(255),
                    candidate_last_name     VARCHAR(255),
                    company_name            VARCHAR(255),
                    campaign_role_title     VARCHAR(255),
                    
                    -- Call-Metriken
                    call_duration_minutes   DECIMAL(10, 2),
                    cost_cents              INTEGER,
                    termination_reason      VARCHAR(100),
                    call_successful         BOOLEAN,
                    
                    -- Qualifikation
                    is_qualified            BOOLEAN,
                    failed_criteria         TEXT,
                    
                    -- Timestamps
                    call_timestamp          TIMESTAMP,
                    processed_at            TIMESTAMP DEFAULT NOW()
                );
                
                -- Index für häufige Queries
                CREATE INDEX IF NOT EXISTS idx_calls_campaign_id ON calls(campaign_id);
                CREATE INDEX IF NOT EXISTS idx_calls_company_name ON calls(company_name);
                CREATE INDEX IF NOT EXISTS idx_calls_call_timestamp ON calls(call_timestamp);
                CREATE INDEX IF NOT EXISTS idx_calls_is_qualified ON calls(is_qualified);
            """)
            
            logger.info("✅ [DATABASE] Tables initialized")
    
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
        
        Args:
            conversation_id: Unique call ID from ElevenLabs
            metadata: Metadata from ElevenLabs transformer
            is_qualified: AI qualification result (None if not evaluated)
            failed_criteria: List of criteria names that were not fulfilled
            
        Returns:
            ID of the inserted row
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
        
        # Format failed criteria as comma-separated string (only if not qualified)
        failed_criteria_str = None
        if is_qualified == False and failed_criteria:
            failed_criteria_str = ", ".join(failed_criteria)
        
        async with pool.acquire() as conn:
            row_id = await conn.fetchval("""
                INSERT INTO calls (
                    conversation_id,
                    campaign_id,
                    agent_id,
                    candidate_first_name,
                    candidate_last_name,
                    company_name,
                    campaign_role_title,
                    call_duration_minutes,
                    cost_cents,
                    termination_reason,
                    call_successful,
                    is_qualified,
                    failed_criteria,
                    call_timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    is_qualified = EXCLUDED.is_qualified,
                    failed_criteria = EXCLUDED.failed_criteria,
                    processed_at = NOW()
                RETURNING id
            """,
                conversation_id,
                metadata.get("campaign_id"),
                metadata.get("agent_id"),
                metadata.get("candidate_first_name"),
                metadata.get("candidate_last_name"),
                metadata.get("company_name"),
                metadata.get("campaign_role_title"),
                duration_minutes,
                metadata.get("cost_cents"),
                metadata.get("termination_reason"),
                metadata.get("call_successful") == "success" if metadata.get("call_successful") else None,
                is_qualified,
                failed_criteria_str,
                call_timestamp
            )
            
            logger.info(f"✅ [DATABASE] Call logged: {conversation_id} (id={row_id})")
            return row_id
    
    @classmethod
    async def get_kpi_summary(cls, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get KPI summary statistics.
        
        Args:
            campaign_id: Optional filter by campaign
            
        Returns:
            Dictionary with KPI metrics
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # Build query with optional campaign filter
            where_clause = ""
            params = []
            if campaign_id:
                where_clause = "WHERE campaign_id = $1"
                params = [campaign_id]
            
            # Total calls
            total_calls = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause}",
                *params
            )
            
            # Successful calls
            successful_calls = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {'AND' if where_clause else 'WHERE'} call_successful = true",
                *params
            )
            
            # Qualified candidates
            qualified_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {'AND' if where_clause else 'WHERE'} is_qualified = true",
                *params
            )
            
            # Not qualified candidates
            not_qualified_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM calls {where_clause} {'AND' if where_clause else 'WHERE'} is_qualified = false",
                *params
            )
            
            # Average call duration
            avg_duration = await conn.fetchval(
                f"SELECT AVG(call_duration_minutes) FROM calls {where_clause} {'AND' if where_clause else 'WHERE'} call_duration_minutes IS NOT NULL",
                *params
            )
            
            # Total cost
            total_cost = await conn.fetchval(
                f"SELECT SUM(cost_cents) FROM calls {where_clause}",
                *params
            )
            
            # Termination reasons distribution
            termination_reasons = await conn.fetch(
                f"""SELECT termination_reason, COUNT(*) as count 
                    FROM calls {where_clause} 
                    {'AND' if where_clause else 'WHERE'} termination_reason IS NOT NULL
                    GROUP BY termination_reason""",
                *params
            )
            
            return {
                "total_calls": total_calls or 0,
                "successful_calls": successful_calls or 0,
                "success_rate": round((successful_calls or 0) / total_calls * 100, 1) if total_calls else 0,
                "qualified_candidates": qualified_count or 0,
                "not_qualified_candidates": not_qualified_count or 0,
                "qualification_rate": round((qualified_count or 0) / total_calls * 100, 1) if total_calls else 0,
                "avg_call_duration_minutes": round(float(avg_duration), 2) if avg_duration else 0,
                "total_cost_cents": total_cost or 0,
                "total_cost_eur": round((total_cost or 0) / 100, 2),
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
        """
        Get list of calls with optional filters.
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            campaign_id: Optional campaign filter
            is_qualified: Optional qualification filter
            
        Returns:
            List of call records
        """
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # Build query
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
        """
        Get statistics on which criteria fail most often.
        
        Args:
            campaign_id: Optional campaign filter
            
        Returns:
            Dictionary mapping criterion name to failure count
        """
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
                    {where_clause}""",
                *params
            )
            
            # Count each criterion
            criteria_counts: Dict[str, int] = {}
            for row in rows:
                if row["failed_criteria"]:
                    for criterion in row["failed_criteria"].split(", "):
                        criterion = criterion.strip()
                        if criterion:
                            criteria_counts[criterion] = criteria_counts.get(criterion, 0) + 1
            
            # Sort by count descending
            return dict(sorted(criteria_counts.items(), key=lambda x: x[1], reverse=True))

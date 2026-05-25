"""
Sync Configuration Loader

Loads configuration from database (as opposed to YAML files).
Used during sync operations.
"""

from typing import List, Optional
from datetime import date
from dataclasses import dataclass

from data.database import DatabaseManager
from data.config.models import RolloverType, PriceType, ConditionType


@dataclass
class DBRolloverConfig:
    """Rollover config from database"""
    config_id: str
    underlying: str
    rollover_type: RolloverType
    price_type: PriceType
    roll_start_days: int
    roll_end_days: int
    threshold: Optional[float]
    condition_type: Optional[ConditionType]
    transaction_cost: float


class SyncConfigLoader:
    """Loads sync configuration from database"""

    def __init__(self):
        self.db = DatabaseManager()

    def get_active_rollover_configs(self, data_source: Optional[str] = None) -> List[DBRolloverConfig]:
        """
        Get active rollover configurations from database

        Args:
            data_source: Filter by data source (optional)

        Returns:
            List of DBRolloverConfig
        """
        sql = """
            SELECT config_id, underlying, rollover_type, price_type,
                   roll_start_days, roll_end_days, threshold,
                   condition_type, transaction_cost
            FROM rollover_configs
            WHERE is_active = TRUE AND update_flag = 1
        """
        params = []

        if data_source:
            sql += " AND data_source = %s"
            params.append(data_source)

        sql += " ORDER BY underlying, config_id"

        result = self.db.execute(sql, tuple(params) if params else None)

        configs = []
        for row in result.fetchall():
            configs.append(DBRolloverConfig(
                config_id=row[0],
                underlying=row[1],
                rollover_type=RolloverType(row[2]),
                price_type=PriceType(row[3]),
                roll_start_days=row[4],
                roll_end_days=row[5],
                threshold=row[6],
                condition_type=ConditionType(row[7]) if row[7] else None,
                transaction_cost=row[8] or 0.0
            ))

        return configs

    def get_config(self, config_id: str) -> Optional[DBRolloverConfig]:
        """Get a specific rollover config"""
        result = self.db.execute("""
            SELECT config_id, underlying, rollover_type, price_type,
                   roll_start_days, roll_end_days, threshold,
                   condition_type, transaction_cost
            FROM rollover_configs
            WHERE config_id = %s
        """, (config_id,))

        row = result.fetchone()
        if not row:
            return None

        return DBRolloverConfig(
            config_id=row[0],
            underlying=row[1],
            rollover_type=RolloverType(row[2]),
            price_type=PriceType(row[3]),
            roll_start_days=row[4],
            roll_end_days=row[5],
            threshold=row[6],
            condition_type=ConditionType(row[7]) if row[7] else None,
            transaction_cost=row[8] or 0.0
        )

    def get_last_sync_date(self, data_source: str) -> Optional[date]:
        """Get last successful sync date for a data source"""
        result = self.db.execute("""
            SELECT MAX(sync_date)
            FROM sync_logs
            WHERE data_source = %s AND status = 'success'
        """, (data_source,))

        row = result.fetchone()
        return row[0] if row and row[0] else None

    def log_sync_start(self, sync_date: date, data_source: str, asset_type: str) -> int:
        """Log sync start, returns log ID"""
        result = self.db.execute("""
            INSERT INTO sync_logs (sync_date, data_source, asset_type, status, started_at)
            VALUES (%s, %s, %s, 'running', CURRENT_TIMESTAMP)
            RETURNING id
        """, (sync_date, data_source, asset_type))

        return result.fetchone()[0]

    def log_sync_complete(
        self,
        log_id: int,
        status: str,
        records_count: int = 0,
        error_message: str = None
    ):
        """Log sync completion"""
        self.db.execute("""
            UPDATE sync_logs
            SET status = %s,
                records_count = %s,
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at))::INTEGER
            WHERE id = %s
        """, (status, records_count, error_message, log_id))

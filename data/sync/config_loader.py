"""
同步配置加载器

从数据库加载配置（而非 YAML 文件）
用于同步操作
"""

from typing import List, Optional
from datetime import date
from dataclasses import dataclass

from data.database import DatabaseManager
from data.config.models import RolloverType, PriceType, ConditionType


@dataclass
class DBRolloverConfig:
    """来自数据库的展期配置"""
    config_id: str
    underlying: str
    roll_type: RolloverType
    price_type: PriceType
    roll_start_days: int
    roll_end_days: int
    threshold: Optional[float]
    condition_type: Optional[ConditionType]
    transaction_cost: float


class SyncConfigLoader:
    """从数据库加载同步配置"""

    def __init__(self):
        self.db = DatabaseManager()

    def get_active_roll_configs(self, data_source: Optional[str] = None) -> List[DBRolloverConfig]:
        """
        从数据库获取活跃的展期配置

        Args:
            data_source: 按数据源筛选（可选）

        Returns:
            DBRolloverConfig 列表
        """
        sql = """
            SELECT config_id, underlying, roll_type, price_type,
                   roll_start_days, roll_end_days, threshold,
                   condition_type, transaction_cost
            FROM roll_configs
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
                roll_type=RolloverType(row[2]),
                price_type=PriceType(row[3]),
                roll_start_days=row[4],
                roll_end_days=row[5],
                threshold=row[6],
                condition_type=ConditionType(row[7]) if row[7] else None,
                transaction_cost=row[8] or 0.0
            ))

        return configs

    def get_config(self, config_id: str) -> Optional[DBRolloverConfig]:
        """获取特定展期配置"""
        result = self.db.execute("""
            SELECT config_id, underlying, roll_type, price_type,
                   roll_start_days, roll_end_days, threshold,
                   condition_type, transaction_cost
            FROM roll_configs
            WHERE config_id = %s
        """, (config_id,))

        row = result.fetchone()
        if not row:
            return None

        return DBRolloverConfig(
            config_id=row[0],
            underlying=row[1],
            roll_type=RolloverType(row[2]),
            price_type=PriceType(row[3]),
            roll_start_days=row[4],
            roll_end_days=row[5],
            threshold=row[6],
            condition_type=ConditionType(row[7]) if row[7] else None,
            transaction_cost=row[8] or 0.0
        )

    def get_last_sync_date(self, data_source: str) -> Optional[date]:
        """获取数据源的最后一次成功同步日期"""
        result = self.db.execute("""
            SELECT MAX(sync_date)
            FROM sync_logs
            WHERE data_source = %s AND status = 'success'
        """, (data_source,))

        row = result.fetchone()
        return row[0] if row and row[0] else None

    def log_sync_start(self, sync_date: date, data_source: str, asset_type: str) -> int:
        """记录同步开始，返回日志 ID"""
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
        """记录同步完成"""
        self.db.execute("""
            UPDATE sync_logs
            SET status = %s,
                records_count = %s,
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at))::INTEGER
            WHERE id = %s
        """, (status, records_count, error_message, log_id))

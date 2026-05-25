"""
Asset Data Manager

Handles CRUD operations for assets and trade calendar.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class AssetManager:
    """资产数据管理器"""

    def __init__(self, connection: DatabaseConnection):
        self._conn = connection

    def save_assets(self, df: pd.DataFrame) -> bool:
        """保存资产信息"""
        if df.empty:
            return False
        try:
            df.to_sql("assets", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to assets")
            return True
        except Exception as e:
            logger.error(f"Failed to save assets: {e}")
            return False

    def get_assets(self, asset_class: Optional[str] = None) -> pd.DataFrame:
        """查询资产列表"""
        sql = "SELECT * FROM assets WHERE is_active = TRUE"
        params = {}
        if asset_class:
            sql += " AND asset_class = :cls"
            params["cls"] = asset_class
        sql += " ORDER BY symbol"

        return self._conn.execute_query(sql, params)

    def save_trade_calendar(self, df: pd.DataFrame) -> bool:
        """保存交易日历"""
        if df.empty:
            return False
        try:
            df.to_sql("trade_calendar", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to trade_calendar")
            return True
        except Exception as e:
            logger.error(f"Failed to save trade calendar: {e}")
            return False

    def get_trade_calendar(
        self,
        market: str = "SSE",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询交易日历"""
        sql = "SELECT * FROM trade_calendar WHERE market = :market"
        params = {"market": market}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

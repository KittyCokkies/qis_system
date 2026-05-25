"""
资产数据管理模块

处理资产信息和交易日历的CRUD操作
管理资产列表和交易日期
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class AssetManager:
    """资产数据管理器

    管理资产基础数据，包括：
    - 资产信息（股票、期货、指数等）
    - 交易日历

    Attributes:
        _conn: 数据库连接对象

    Example:
        >>> db = DatabaseConnection()
        >>> am = AssetManager(db)
        >>> assets = am.get_assets(asset_class='future')
    """

    def __init__(self, connection: DatabaseConnection):
        """初始化资产管理器

        Args:
            connection: 数据库连接对象
        """
        self._conn = connection

    # ==================== 资产信息操作 ====================

    def save_assets(self, df: pd.DataFrame) -> bool:
        """保存资产信息

        将资产列表写入assets表

        Args:
            df: DataFrame，包含列：[symbol, underlying, name, asset_class, exchange, ...]

        Returns:
            bool: 保存成功返回True
        """
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
        """查询资产列表

        从assets表查询资产信息

        Args:
            asset_class: 资产类别筛选，如 'stock'/'future'/'index'

        Returns:
            pd.DataFrame: 资产列表
        """
        sql = "SELECT * FROM assets WHERE is_active = TRUE"
        params = {}
        if asset_class:
            sql += " AND asset_class = :cls"
            params["cls"] = asset_class
        sql += " ORDER BY symbol"

        return self._conn.execute_query(sql, params)

    # ==================== 交易日历操作 ====================

    def save_trade_calendar(self, df: pd.DataFrame) -> bool:
        """保存交易日历

        将交易日历写入trade_calendar表

        Args:
            df: DataFrame，包含列：[date, market, is_trading_day, ...]

        Returns:
            bool: 保存成功返回True
        """
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
        """查询交易日历

        从trade_calendar表查询交易日信息

        Args:
            market: 市场代码，如 "SSE"（上交所）、"SZSE"（深交所）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 交易日历数据
        """
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

"""
Hedge Data Manager

Handles CRUD operations for hedge instruments and synthetic indices.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class HedgeManager:
    """对冲数据管理器"""

    def __init__(self, connection: DatabaseConnection):
        self._conn = connection

    def save_hedge_instrument_mapping(self, df: pd.DataFrame) -> bool:
        """保存对冲工具映射关系"""
        if df.empty:
            return False
        try:
            df.to_sql("hedge_instrument_mapping", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to hedge_instrument_mapping")
            return True
        except Exception as e:
            logger.error(f"Failed to save hedge mapping: {e}")
            return False

    def get_hedge_instruments(
        self,
        underlying_index: str,
        hedge_type: Optional[str] = None,
        active_only: bool = True,
    ) -> pd.DataFrame:
        """查询标的指数的对冲工具列表

        Args:
            underlying_index: 标的指数，如 "000300.SH"
            hedge_type: 筛选特定对冲类型
            active_only: 只返回可用状态的工具
        """
        sql = "SELECT * FROM hedge_instrument_mapping WHERE underlying_index = :idx"
        params = {"idx": underlying_index}

        if active_only:
            sql += " AND is_active = TRUE"
        if hedge_type:
            sql += " AND hedge_type = :type"
            params["type"] = hedge_type
        sql += " ORDER BY priority, hedge_symbol"

        return self._conn.execute_query(sql, params)

    def save_synthetic_index(self, df: pd.DataFrame) -> bool:
        """保存合成指数序列"""
        if df.empty:
            return False
        try:
            df.to_sql("synthetic_index_series", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to synthetic_index_series")
            return True
        except Exception as e:
            logger.error(f"Failed to save synthetic index: {e}")
            return False

    def get_synthetic_index(
        self,
        underlying_index: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询合成指数序列"""
        sql = "SELECT * FROM synthetic_index_series WHERE underlying_index = :idx"
        params = {"idx": underlying_index}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    def save_strategy_index_series(self, df: pd.DataFrame) -> bool:
        """保存策略指数序列（不同对冲工具下的策略表现）"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_index_series", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_index_series")
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy index: {e}")
            return False

    def get_strategy_index_series(
        self,
        strategy_code: str,
        underlying_index: Optional[str] = None,
        hedge_symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略指数序列

        Returns:
            DataFrame: 包含不同对冲工具下的策略指数点位
        """
        sql = "SELECT * FROM strategy_index_series WHERE strategy_code = :code"
        params = {"code": strategy_code}

        if underlying_index:
            sql += " AND underlying_index = :underlying"
            params["underlying"] = underlying_index
        if hedge_symbol:
            sql += " AND hedge_symbol = :hedge"
            params["hedge"] = hedge_symbol
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date, hedge_symbol"

        return self._conn.execute_query(sql, params)

    def compare_hedge_instruments(
        self,
        strategy_code: str,
        underlying_index: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """比较同一策略不同对冲工具的表现"""
        if date is None:
            date = datetime.now()

        sql = """
        SELECT
            s1.hedge_symbol as hedge_1,
            s1.hedge_type as type_1,
            s1.index_value as value_1,
            s1.cumulative_return as return_1,
            s1.hedge_cost as cost_1,
            s2.hedge_symbol as hedge_2,
            s2.hedge_type as type_2,
            s2.index_value as value_2,
            s2.cumulative_return as return_2,
            s2.hedge_cost as cost_2,
            s1.cumulative_return - s2.cumulative_return as return_diff,
            s1.hedge_cost - s2.hedge_cost as cost_diff
        FROM strategy_index_series s1
        JOIN strategy_index_series s2
            ON s1.strategy_code = s2.strategy_code
            AND s1.underlying_index = s2.underlying_index
            AND s1.date = s2.date
        WHERE s1.strategy_code = :code
        AND s1.underlying_index = :underlying
        AND s1.date = :date
        AND s1.hedge_symbol < s2.hedge_symbol
        ORDER BY ABS(s1.cumulative_return - s2.cumulative_return) DESC
        """

        return self._conn.execute_query(sql, {
            "code": strategy_code,
            "underlying": underlying_index,
            "date": date
        })

    def save_strategy_hedge_config(self, df: pd.DataFrame) -> bool:
        """保存策略对冲配置"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_hedge_config", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_hedge_config")
            return True
        except Exception as e:
            logger.error(f"Failed to save hedge config: {e}")
            return False

    def get_strategy_hedge_config(
        self,
        strategy_code: str,
        underlying_index: Optional[str] = None,
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略对冲配置"""
        if as_of_date is None:
            as_of_date = datetime.now()

        sql = """
        SELECT * FROM strategy_hedge_config
        WHERE strategy_code = :code
        AND effective_date <= :date
        AND (expiry_date IS NULL OR expiry_date > :date)
        AND is_active = TRUE
        """
        params = {"code": strategy_code, "date": as_of_date}

        if underlying_index:
            sql += " AND underlying_index = :underlying"
            params["underlying"] = underlying_index
        sql += " ORDER BY effective_date DESC"

        return self._conn.execute_query(sql, params)

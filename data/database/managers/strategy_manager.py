"""
Strategy Data Manager

Handles CRUD operations for strategy NAV, positions, and trades.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class StrategyManager:
    """策略数据管理器"""

    def __init__(self, connection: DatabaseConnection):
        self._conn = connection

    def save_strategy_nav(self, df: pd.DataFrame) -> bool:
        """保存策略净值数据"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_nav", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_nav")
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy NAV: {e}")
            return False

    def get_strategy_nav(
        self,
        strategy_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略净值"""
        sql = "SELECT * FROM strategy_nav WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    def save_target_positions(self, df: pd.DataFrame) -> bool:
        """保存目标持仓（策略信号）"""
        if df.empty:
            return False
        try:
            df.to_sql("target_positions", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to target_positions")
            return True
        except Exception as e:
            logger.error(f"Failed to save target positions: {e}")
            return False

    def get_target_positions(
        self,
        strategy_code: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询目标持仓"""
        sql = "SELECT * FROM target_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        return self._conn.execute_query(sql, params)

    def save_actual_positions(self, df: pd.DataFrame) -> bool:
        """保存实际持仓"""
        if df.empty:
            return False
        try:
            df.to_sql("actual_positions", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to actual_positions")
            return True
        except Exception as e:
            logger.error(f"Failed to save actual positions: {e}")
            return False

    def get_actual_positions(
        self,
        strategy_code: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询实际持仓"""
        sql = "SELECT * FROM actual_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        return self._conn.execute_query(sql, params)

    def save_trades(self, df: pd.DataFrame) -> bool:
        """保存交易记录"""
        if df.empty:
            return False
        try:
            df.to_sql("trades", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to trades")
            return True
        except Exception as e:
            logger.error(f"Failed to save trades: {e}")
            return False

    def get_trades(
        self,
        strategy_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询交易记录"""
        sql = "SELECT * FROM trades WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if start_date:
            sql += " AND trade_date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND trade_date <= :end"
            params["end"] = end_date
        sql += " ORDER BY trade_date DESC, trade_time DESC"

        return self._conn.execute_query(sql, params)

    def save_roll_execution(self, df: pd.DataFrame) -> bool:
        """保存期货展期执行记录"""
        if df.empty:
            return False
        try:
            df.to_sql("roll_executions", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to roll_executions")
            return True
        except Exception as e:
            logger.error(f"Failed to save roll executions: {e}")
            return False

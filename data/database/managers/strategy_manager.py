"""
策略数据管理模块

处理策略净值、持仓、交易记录等数据的CRUD操作
支持策略业绩跟踪和实盘监控
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class StrategyManager:
    """策略数据管理器

    管理策略相关的所有数据，包括：
    - 策略净值序列（NAV）
    - 目标持仓（策略信号）
    - 实际持仓（执行结果）
    - 交易记录
    - 期货展期执行记录

    Attributes:
        _conn: 数据库连接对象

    Example:
        >>> db = DatabaseConnection()
        >>> sm = StrategyManager(db)
        >>> nav_df = sm.get_strategy_nav("STRATEGY_001")
    """

    def __init__(self, connection: DatabaseConnection):
        """初始化策略管理器

        Args:
            connection: 数据库连接对象
        """
        self._conn = connection

    # ==================== 策略净值操作 ====================

    def save_strategy_nav(self, df: pd.DataFrame) -> bool:
        """保存策略净值数据

        将策略每日净值写入strategy_nav表

        Args:
            df: DataFrame，包含列：[strategy_code, date, nav, daily_return, ...]

        Returns:
            bool: 保存成功返回True
        """
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
        """查询策略净值

        从strategy_nav表查询策略历史净值

        Args:
            strategy_code: 策略代码，如 "STRATEGY_001"
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 策略净值数据
        """
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

    # ==================== 持仓操作 ====================

    def save_target_positions(self, df: pd.DataFrame) -> bool:
        """保存目标持仓（策略信号）

        将策略生成的目标权重写入target_positions表

        Args:
            df: DataFrame，包含列：[strategy_code, symbol, date, target_weight, ...]

        Returns:
            bool: 保存成功返回True
        """
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
        """查询目标持仓

        从target_positions表查询策略的目标持仓配置

        Args:
            strategy_code: 策略代码
            date: 查询日期，None表示查询最新持仓

        Returns:
            pd.DataFrame: 目标持仓数据
        """
        sql = "SELECT * FROM target_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        return self._conn.execute_query(sql, params)

    def save_actual_positions(self, df: pd.DataFrame) -> bool:
        """保存实际持仓

        将实际执行后的持仓写入actual_positions表

        Args:
            df: DataFrame，包含实际持仓数据

        Returns:
            bool: 保存成功返回True
        """
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
        """查询实际持仓

        从actual_positions表查询实际持仓情况

        Args:
            strategy_code: 策略代码
            date: 查询日期

        Returns:
            pd.DataFrame: 实际持仓数据
        """
        sql = "SELECT * FROM actual_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        return self._conn.execute_query(sql, params)

    # ==================== 交易记录操作 ====================

    def save_trades(self, df: pd.DataFrame) -> bool:
        """保存交易记录

        将成交记录写入trades表

        Args:
            df: DataFrame，包含列：[strategy_code, symbol, trade_date, direction, quantity, price, ...]

        Returns:
            bool: 保存成功返回True
        """
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
        """查询交易记录

        从trades表查询历史交易

        Args:
            strategy_code: 策略代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 交易记录
        """
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

    # ==================== 展期操作 ====================

    def save_roll_execution(self, df: pd.DataFrame) -> bool:
        """保存期货展期执行记录

        将期货合约换月记录写入roll_executions表

        Args:
            df: DataFrame，包含列：[strategy_code, underlying, roll_date, from_contract, to_contract, ...]

        Returns:
            bool: 保存成功返回True
        """
        if df.empty:
            return False
        try:
            df.to_sql("roll_executions", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to roll_executions")
            return True
        except Exception as e:
            logger.error(f"Failed to save roll executions: {e}")
            return False

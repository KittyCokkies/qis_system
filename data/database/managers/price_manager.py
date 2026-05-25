"""
价格数据管理模块

处理股票、期货、指数等资产的价格数据CRUD操作
提供统一的价格查询接口
"""

from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class PriceManager:
    """价格数据管理器

    管理各类资产的价格数据，包括：
    - 股票价格（前复权）
    - 期货原始合约价格
    - 期货连续合约价格（展期后）
    - 指数价格

    Attributes:
        _conn: 数据库连接对象

    Example:
        >>> db = DatabaseConnection()
        >>> pm = PriceManager(db)
        >>> df = pm.get_stock_prices("000300.SH", start_date="2024-01-01")
    """

    def __init__(self, connection: DatabaseConnection):
        """初始化价格管理器

        Args:
            connection: 数据库连接对象
        """
        self._conn = connection

    # ==================== 股票价格操作 ====================

    def save_stock_prices(self, df: pd.DataFrame) -> bool:
        """保存股票价格数据（前复权）

        将股票日频数据写入prices_stock表

        Args:
            df: DataFrame，包含列：[symbol, date, open, high, low, close, volume, amount, ...]

        Returns:
            bool: 保存成功返回True，失败返回False

        Example:
            >>> df = pd.DataFrame({
            ...     'symbol': ['000001.SZ'],
            ...     'date': ['2024-01-01'],
            ...     'close': [10.5]
            ... })
            >>> pm.save_stock_prices(df)
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_stock", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_stock")
            return True
        except Exception as e:
            logger.error(f"Failed to save stock prices: {e}")
            return False

    def get_stock_prices(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """查询股票价格

        从prices_stock表查询股票价格数据

        Args:
            symbol: 股票代码或代码列表，如 "000001.SZ" 或 ["000001.SZ", "000002.SZ"]
            start_date: 开始日期
            end_date: 结束日期
            fields: 返回字段列表，None表示返回所有字段

        Returns:
            pd.DataFrame: 价格数据

        Example:
            >>> df = pm.get_stock_prices("000300.SH", start_date="2024-01-01")
        """
        if isinstance(symbol, str):
            symbol = [symbol]
        symbols_str = ",".join([f"'{s}'" for s in symbol])
        field_str = ",".join(fields) if fields else "*"

        sql = f"SELECT {field_str} FROM prices_stock WHERE symbol IN ({symbols_str})"
        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    # ==================== 期货价格操作 ====================

    def save_future_prices(self, df: pd.DataFrame) -> bool:
        """保存期货原始合约价格数据

        将期货合约日频数据写入prices_future表

        Args:
            df: DataFrame，包含期货原始合约价格数据

        Returns:
            bool: 保存成功返回True
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_future", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_future")
            return True
        except Exception as e:
            logger.error(f"Failed to save future prices: {e}")
            return False

    def get_future_prices(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """查询期货价格

        从prices_future表查询期货原始合约价格

        Args:
            symbol: 合约代码或列表，如 "IF2401"
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 期货价格数据
        """
        if isinstance(symbol, str):
            symbol = [symbol]
        symbols_str = ",".join([f"'{s}'" for s in symbol])

        sql = f"SELECT * FROM prices_future WHERE symbol IN ({symbols_str})"
        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    # ==================== 期货连续合约操作 ====================

    def save_future_continuous(self, df: pd.DataFrame) -> bool:
        """保存期货连续合约价格（展期后）

        将展期处理后的连续合约价格写入prices_future_continuous表

        Args:
            df: DataFrame，包含连续合约价格数据

        Returns:
            bool: 保存成功返回True
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_future_continuous", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_future_continuous")
            return True
        except Exception as e:
            logger.error(f"Failed to save continuous prices: {e}")
            return False

    def get_future_continuous(
        self,
        underlying: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        roll_start_days: int = 10,
        roll_end_days: int = 3
    ) -> pd.DataFrame:
        """查询期货连续合约价格

        从prices_future_continuous表查询展期后的连续价格

        Args:
            underlying: 品种代码，如 "IF"（沪深300股指）
            start_date: 开始日期
            end_date: 结束日期
            roll_start_days: 观察窗口开始p（到期前p天开始观察）
            roll_end_days: 强制展期q（到期前q天强制换月）

        Returns:
            pd.DataFrame: 连续合约价格数据

        Example:
            >>> df = pm.get_future_continuous("IF", roll_start_days=7, roll_end_days=4)
        """
        sql = """
            SELECT * FROM prices_future_continuous
            WHERE underlying = :underlying
            AND roll_start_days = :p AND roll_end_days = :q
        """
        params = {"underlying": underlying, "p": roll_start_days, "q": roll_end_days}

        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    # ==================== 指数价格操作 ====================

    def save_index_prices(self, df: pd.DataFrame) -> bool:
        """保存指数价格数据

        将指数日频数据写入prices_index表

        Args:
            df: DataFrame，包含指数价格数据

        Returns:
            bool: 保存成功返回True
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_index", self._conn.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_index")
            return True
        except Exception as e:
            logger.error(f"Failed to save index prices: {e}")
            return False

    def get_index_prices(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """查询指数价格

        从prices_index表查询指数价格数据

        Args:
            symbol: 指数代码或列表，如 "000300.SH"
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 指数价格数据
        """
        if isinstance(symbol, str):
            symbol = [symbol]
        symbols_str = ",".join([f"'{s}'" for s in symbol])

        sql = f"SELECT * FROM prices_index WHERE symbol IN ({symbols_str})"
        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        return self._conn.execute_query(sql, params)

    # ==================== 统一价格查询接口 ====================

    def get_daily_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """统一价格查询接口（智能识别资产类型）

        根据symbol自动判断资产类型，从相应表中查询价格

        Args:
            symbol: 资产代码，如 "000300.SH"（指数）、"IF2401"（期货合约）
            start_date: 开始日期
            end_date: 结束日期
            fields: 返回字段列表

        Returns:
            pd.DataFrame: 价格数据，包含asset_class列标识资产类型

        Example:
            >>> df = pm.get_daily_price("000300.SH")  # 自动识别为指数
            >>> df = pm.get_daily_price("IF")  # 尝试查询连续合约
        """
        field_str = ",".join(fields) if fields else "*"

        # 尝试股票表
        sql = f"SELECT {field_str}, 'stock' as asset_class FROM prices_stock WHERE symbol = :symbol"
        params = {"symbol": symbol}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date

        result = self._conn.execute_query(sql, params)
        if not result.empty:
            return result

        # 尝试指数表
        sql = f"SELECT {field_str}, 'index' as asset_class FROM prices_index WHERE symbol = :symbol"
        result = self._conn.execute_query(sql, params)
        if not result.empty:
            return result

        # 尝试期货连续
        sql = f"""
            SELECT date, continuous_price as close, underlying as symbol, 'future' as asset_class
            FROM prices_future_continuous
            WHERE underlying = :symbol
        """
        if start_date:
            sql += " AND date >= :start_date"
        if end_date:
            sql += " AND date <= :end_date"
        sql += " ORDER BY date LIMIT 1"

        result = self._conn.execute_query(sql, params)
        if not result.empty:
            return result

        logger.warning(f"No price data found for symbol: {symbol}")
        return pd.DataFrame()

    def save_daily_price(self, df: pd.DataFrame, asset_class: str = 'stock') -> bool:
        """保存日线数据（根据资产类型自动路由）

        根据asset_class自动选择对应的保存方法

        Args:
            df: DataFrame，价格数据
            asset_class: 资产类型，'stock'/'future'/'index'

        Returns:
            bool: 保存成功返回True
        """
        if asset_class == 'stock':
            return self.save_stock_prices(df)
        elif asset_class == 'future':
            return self.save_future_prices(df)
        elif asset_class == 'index':
            return self.save_index_prices(df)
        else:
            logger.error(f"Unknown asset class: {asset_class}")
            return False

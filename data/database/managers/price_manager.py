"""
Price Data Manager

Handles CRUD operations for stock, future, and index prices.
"""

from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
from loguru import logger
from sqlalchemy import text

from data.database.connection import DatabaseConnection


class PriceManager:
    """价格数据管理器"""

    def __init__(self, connection: DatabaseConnection):
        self._conn = connection

    # ==================== Stock Prices ====================

    def save_stock_prices(self, df: pd.DataFrame) -> bool:
        """保存股票价格数据（前复权）"""
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
        """查询股票价格"""
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

    # ==================== Future Prices ====================

    def save_future_prices(self, df: pd.DataFrame) -> bool:
        """保存期货原始合约价格数据"""
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
        """查询期货价格"""
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

    # ==================== Future Continuous ====================

    def save_future_continuous(self, df: pd.DataFrame) -> bool:
        """保存期货连续合约价格（展期后）"""
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
        """查询期货连续合约价格"""
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

    # ==================== Index Prices ====================

    def save_index_prices(self, df: pd.DataFrame) -> bool:
        """保存指数价格数据"""
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
        """查询指数价格"""
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

    # ==================== Unified Price Query ====================

    def get_daily_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """统一价格查询接口（智能识别资产类型）"""
        field_str = ",".join(fields) if fields else "*"

        # Try stock table
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

        # Try index table
        sql = f"SELECT {field_str}, 'index' as asset_class FROM prices_index WHERE symbol = :symbol"
        result = self._conn.execute_query(sql, params)
        if not result.empty:
            return result

        # Try future continuous
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
        """保存日线数据（根据资产类型自动路由）"""
        if asset_class == 'stock':
            return self.save_stock_prices(df)
        elif asset_class == 'future':
            return self.save_future_prices(df)
        elif asset_class == 'index':
            return self.save_index_prices(df)
        else:
            logger.error(f"Unknown asset class: {asset_class}")
            return False

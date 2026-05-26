"""
Concat Asset Builder

Builds synthetic continuous assets by concatenating multiple data sources.

Example: CYB_CONCAT = 创业板指 (2010-05-31 to 2011-11-15) + 创业板ETF (2011-11-16 onwards)
"""

from datetime import date
from typing import List, Optional
import pandas as pd
from loguru import logger

from data.config.loader import AssetConfigLoader
from data.config.models import ConcatAsset
from data.database import DatabaseManager


class ConcatBuilder:
    """构建拼接资产"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()

    def get_active_assets(self) -> List[ConcatAsset]:
        """Get active concat assets"""
        return [
            asset for asset in self.config_loader.get_all_concat_assets()
            if asset.update_flag == 1
        ]

    def build_for_date(self, symbol: str, build_date: date) -> int:
        """
        Build concat asset for a specific date

        Args:
            symbol: Concat asset symbol (e.g., 'CYB_CONCAT')
            build_date: Date to build

        Returns:
            Number of records created (0 or 1)
        """
        asset = self.config_loader.get_concat_asset(symbol)
        if not asset:
            raise ValueError(f"Unknown concat asset: {symbol}")

        # 查找该日期哪个成分处于活跃状态
        component = asset.get_component_for_date(build_date)
        if not component:
            logger.debug(f"No component for {symbol} on {build_date}")
            return 0

        # 获取成分的价格数据
        price = self._get_component_price(component.symbol, build_date)

        if price is None:
            logger.debug(f"No price for component {component.symbol} on {build_date}")
            return 0

        # Store concat price
        self._store_concat_price(symbol, build_date, price, component.symbol)

        return 1

    def build_for_range(self, symbol: str, start_date: date, end_date: date) -> int:
        """
        Build concat asset for a date range

        Args:
            symbol: Concat asset symbol
            start_date: Start date
            end_date: End date

        Returns:
            Number of records created
        """
        from datetime import timedelta

        count = 0
        current = start_date
        while current <= end_date:
            try:
                if self.build_for_date(symbol, current) > 0:
                    count += 1
            except Exception as e:
                logger.error(f"Failed to build {symbol} for {current}: {e}")
            current += timedelta(days=1)

        logger.info(f"Built {count} concat records for {symbol}")
        return count

    def build_all(self, build_date: date) -> int:
        """
        Build all concat assets for a date

        Returns:
            Total number of records created
        """
        assets = self.get_active_assets()
        total = 0

        for asset in assets:
            try:
                total += self.build_for_date(asset.symbol, build_date)
            except Exception as e:
                logger.error(f"Failed to build {asset.symbol}: {e}")

        return total

    def _get_component_price(self, symbol: str, query_date: date) -> Optional[float]:
        """
        Get closing price for a component

        Checks multiple tables based on symbol type
        """
        # Try prices_index
        result = self.db.execute("""
            SELECT close FROM prices_index
            WHERE symbol = %s AND date = %s
        """, (symbol, query_date))

        row = result.fetchone()
        if row and row[0]:
            return row[0]

        # Try prices_stock (for ETFs)
        result = self.db.execute("""
            SELECT close FROM prices_stock
            WHERE symbol = %s AND date = %s
        """, (symbol, query_date))

        row = result.fetchone()
        if row and row[0]:
            return row[0]

        # Try prices_future_continuous (for futures-based components)
        # Extract config_id from symbol if it's a continuous contract
        if '_S' in symbol or '_D' in symbol:
            result = self.db.execute("""
                SELECT continuous_price FROM prices_future_continuous
                WHERE config_id = %s AND date = %s
            """, (symbol, query_date))

            row = result.fetchone()
            if row and row[0]:
                return row[0]

        return None

    def _store_concat_price(
        self,
        symbol: str,
        query_date: date,
        price: float,
        source_symbol: str
    ):
        """Store concat price to database"""
        # Check if concat_assets table exists, if not use prices_index
        # For simplicity, storing in a dedicated table

        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS prices_concat (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(30) NOT NULL,
                    date DATE NOT NULL,
                    close DECIMAL(12, 4),
                    source_symbol VARCHAR(30),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """)
        except:
            pass  # Table might already exist

        self.db.execute("""
            INSERT INTO prices_concat (symbol, date, close, source_symbol)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                close = EXCLUDED.close,
                source_symbol = EXCLUDED.source_symbol
        """, (symbol, query_date, price, source_symbol))

        logger.debug(f"Stored concat price for {symbol} on {query_date}: {price}")

    def get_concat_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Get concat asset history as DataFrame

        Args:
            symbol: Concat asset symbol
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with columns: date, close, source_symbol
        """
        result = self.db.execute("""
            SELECT date, close, source_symbol
            FROM prices_concat
            WHERE symbol = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """, (symbol, start_date, end_date))

        rows = result.fetchall()
        if not rows:
            return pd.DataFrame(columns=['date', 'close', 'source_symbol'])

        return pd.DataFrame(rows, columns=['date', 'close', 'source_symbol'])

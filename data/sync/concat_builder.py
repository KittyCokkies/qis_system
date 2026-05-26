"""
拼接资产构建器

通过拼接多个数据源构建合成连续资产

示例: CYB_CONCAT = 创业板指 (2010-05-31 至 2011-11-15) + 创业板ETF (2011-11-16 起)
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
        """获取活跃的拼接资产"""
        return [
            asset for asset in self.config_loader.get_all_concat_assets()
            if asset.update_flag == 1
        ]

    def build_for_date(self, symbol: str, build_date: date) -> int:
        """
        为特定日期构建拼接资产

        Args:
            symbol: 拼接资产代码 (如 'CYB_CONCAT')
            build_date: 构建日期

        Returns:
            创建的记录数 (0 或 1)
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
        为日期范围构建拼接资产

        Args:
            symbol: 拼接资产代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            创建的记录数
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
        为某日期构建所有拼接资产

        Returns:
            创建的记录总数
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
        获取成分收盘价

        根据代码类型检查多个表
        """
        # 尝试 prices_index
        result = self.db.execute("""
            SELECT close FROM prices_index
            WHERE symbol = %s AND date = %s
        """, (symbol, query_date))

        row = result.fetchone()
        if row and row[0]:
            return row[0]

        # 尝试 prices_stock（用于ETF）
        result = self.db.execute("""
            SELECT close FROM prices_stock
            WHERE symbol = %s AND date = %s
        """, (symbol, query_date))

        row = result.fetchone()
        if row and row[0]:
            return row[0]

        # 尝试 prices_future_continuous（用于期货成分）
        # 如果是连续合约，从代码中提取 config_id
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
        """将拼接价格存储到数据库"""
        # 检查 concat_assets 表是否存在，不存在则使用 prices_index
        # 为简化，存储在专用表中

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
        获取拼接资产历史为 DataFrame

        Args:
            symbol: 拼接资产代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            列名为 date, close, source_symbol 的 DataFrame
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

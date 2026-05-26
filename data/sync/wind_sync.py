"""
Wind 数据同步

从 Wind 同步指数和 ETF 数据
"""

from datetime import date
from typing import List
from loguru import logger

from data.wind_source import WindSource
from data.config.loader import AssetConfigLoader, IndexAsset, ETFAsset
from data.database import DatabaseManager


class WindSync:
    """Wind 数据同步器"""

    def __init__(self):
        self.source = WindSource()
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._connected = False

    def connect(self) -> bool:
        """连接到 Wind"""
        try:
            self.source.connect()
            self._connected = True
            logger.info("已连接到 Wind")
            return True
        except Exception as e:
            logger.error(f"连接 Wind 失败: {e}")
            return False

    def disconnect(self):
        """断开与 Wind 的连接"""
        if self._connected:
            self.source.close()
            self._connected = False
            logger.info("已断开与 Wind 的连接")

    def get_active_indices(self) -> List[IndexAsset]:
        """从配置获取活跃指数"""
        return [idx for idx in self.config_loader.get_all_indices() if idx.update_flag == 1]

    def get_active_etfs(self) -> List[ETFAsset]:
        """从配置获取活跃 ETF"""
        return [etf for etf in self.config_loader.get_all_etfs() if etf.update_flag == 1]

    def sync_index_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """同步指数日频数据"""
        if not self._connected:
            raise RuntimeError("未连接到 Wind")

        try:
            # 使用 Wind API 获取日频数据
            df = self.source.get_daily_price(symbol, sync_date, sync_date)

            if df.empty:
                logger.debug(f"{symbol} 在 {sync_date} 无数据")
                return 0

            # 插入数据库
            record = df.iloc[0].to_dict()

            if full_refresh:
                self.db.execute(
                    "DELETE FROM prices_index WHERE symbol = %s AND date = %s",
                    (symbol, sync_date)
                )

            self.db.execute("""
                INSERT INTO prices_index
                (symbol, date, open, high, low, close, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount
            """, (
                symbol, sync_date,
                record.get('open'), record.get('high'),
                record.get('low'), record.get('close'),
                record.get('volume'), record.get('amount')
            ))

            return 1

        except Exception as e:
            logger.error(f"同步 {symbol} 失败: {e}")
            return 0

    def sync_etf_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """同步 ETF 日频数据（视为股票）"""
        # ETF 与指数同步方式类似，但存储在 prices_stock 中
        # 实现占位符
        return 0

    def sync_index_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """同步指数历史数据"""
        if not self._connected:
            raise RuntimeError("未连接到 Wind")

        try:
            df = self.source.get_daily_price(symbol, start_date, end_date)

            if df.empty:
                logger.warning(f"{symbol} 从 {start_date} 到 {end_date} 无数据")
                return 0

            # 批量插入
            records = df.reset_index().to_dict('records')
            for record in records:
                self.db.execute("""
                    INSERT INTO prices_index
                    (symbol, date, open, high, low, close, volume, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        amount = EXCLUDED.amount
                """, (
                    symbol, record.get('date'),
                    record.get('open'), record.get('high'),
                    record.get('low'), record.get('close'),
                    record.get('volume'), record.get('amount')
                ))

            return len(records)

        except Exception as e:
            logger.error(f"同步 {symbol} 历史数据失败: {e}")
            return 0

    def sync_etf_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """同步 ETF 历史数据"""
        # 实现占位符
        return 0

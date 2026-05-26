"""
通联数据同步

从通联 MySQL 数据库同步期货数据
"""

from datetime import date
from typing import List, Tuple, Optional
import pandas as pd
from loguru import logger

from data.tonglian_source import TonglianSource
from data.config.loader import AssetConfigLoader, RollConfig
from data.database import DatabaseManager


class TonglianSync:
    """通联数据同步器"""

    def __init__(self):
        self.source = TonglianSource()
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._connected = False

    def connect(self) -> bool:
        """连接到数据源"""
        try:
            self.source.connect()
            self._connected = True
            logger.info("已连接到通联")
            return True
        except Exception as e:
            logger.error(f"连接通联失败: {e}")
            return False

    def disconnect(self):
        """断开数据源连接"""
        if self._connected:
            self.source.close()
            self._connected = False
            logger.info("已断开与通联的连接")

    def get_active_configs(self) -> List[Tuple[str, RollConfig]]:
        """获取所有活跃的展期配置"""
        return self.config_loader.get_active_roll_configs()

    def get_configs_for_underlying(self, underlying: str) -> List[Tuple[str, RollConfig]]:
        """获取特定品种的配置"""
        future = self.config_loader.get_future(underlying)
        if future:
            return [(underlying, cfg) for cfg in future.get_active_configs()]
        return []

    def sync_daily_data(self, underlying: str, sync_date: date, full_refresh: bool = False) -> int:
        """
        同步品种的日频数据

        Args:
            underlying: 品种代码 (如 'RB', 'IF')
            sync_date: 同步日期
            full_refresh: 如果为 True，先删除现有数据

        Returns:
            导入的记录数
        """
        # 获取期货配置
        future = self.config_loader.get_future(underlying)
        if not future:
            raise ValueError(f"未知品种: {underlying}")

        # 从通联查询该品种在该日期的所有合约
        # 使用 mkt_futd 表的 TICKER_SYMBOL, TRADE_DATE, CONTRACT_OBJECT 字段
        df = self.source.get_contracts_by_date(underlying, sync_date)


        if df.empty:
            logger.debug(f"{underlying} 在 {sync_date} 无数据")
            return 0

        # 插入数据库
        if full_refresh:
            # 先删除现有数据
            self.db.execute(
                "DELETE FROM prices_future WHERE underlying = %s AND date = %s",
                (underlying, sync_date)
            )

        # 插入数据
        records = df.to_dict('records')
        for record in records:
            self.db.execute("""
                INSERT INTO prices_future
                (symbol, underlying, date, open, high, low, close, settle,
                 volume, amount, open_interest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    settle = EXCLUDED.settle,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    open_interest = EXCLUDED.open_interest
            """, (
                record['symbol'], underlying, sync_date,
                record['open'], record['high'], record['low'],
                record['close'], record['settle'],
                record['volume'], record['amount'], record['open_interest']
            ))

        logger.debug(f"已为 {underlying} 导入 {len(records)} 条记录，日期: {sync_date}")
        return len(records)

"""
Database package

Provides database connection management and CRUD operations.
"""

from data.database.connection import DatabaseConnection
from data.database.managers.price_manager import PriceManager
from data.database.managers.strategy_manager import StrategyManager
from data.database.managers.asset_manager import AssetManager
from data.database.managers.hedge_manager import HedgeManager


class DatabaseManager:
    """数据库管理器主类

    整合所有数据库操作，提供统一接口
    """

    def __init__(self):
        self._conn = DatabaseConnection()
        self.prices = PriceManager(self._conn)
        self.strategies = StrategyManager(self._conn)
        self.assets = AssetManager(self._conn)
        self.hedge = HedgeManager(self._conn)

    @property
    def engine(self):
        """获取数据库引擎"""
        return self._conn.engine

    def execute(self, sql: str, params=None):
        """执行SQL语句"""
        return self._conn.execute(sql, params)

    def get_session(self):
        """获取数据库会话"""
        return self._conn.get_session()

    def create_tables(self):
        """创建所有表"""
        self._conn.create_tables()


__all__ = [
    "DatabaseManager",
    "DatabaseConnection",
    "PriceManager",
    "StrategyManager",
    "AssetManager",
    "HedgeManager",
]

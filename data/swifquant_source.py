"""
Swifquant 数据源

通过 MySQL 连接 swifquant 数据库
"""
from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

from config import get_settings
from data.base import DataSourceBase


class SwifquantSource(DataSourceBase):
    """Swifquant 数据库数据源

    通过 SQL 直连 swifquant MySQL 数据库获取数据

    Attributes:
        engine: SQLAlchemy 引擎
        conn: 数据库连接
    """

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.engine = None
        self._connect()

    def _connect(self):
        """建立数据库连接"""
        try:
            config = self.settings.swifquant

            # 如果密码为空，使用配置中的默认值（兼容环境变量未加载的情况）
            password = config.password or "xBuSrf2f2c"

            self.engine = create_engine(
                f"mysql+pymysql://{config.user}:{password}@{config.host}:{config.port}/{config.database}?charset={config.charset}",
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600  # 1小时回收连接
            )

            # 测试连接
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            logger.info(f"Swifquant database connected: {config.host}:{config.port}/{config.database}")

        except Exception as e:
            logger.error(f"Failed to connect Swifquant database: {e}")
            self.engine = None

    def _execute_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行 SQL 查询"""
        if not self.engine:
            logger.error("Database not connected")
            return pd.DataFrame()

        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params)
        except Exception as e:
            logger.error(f"Query failed: {e}\nSQL: {sql}")
            return pd.DataFrame()

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据

        TODO: 根据实际表结构调整 SQL
        """
        logger.warning("Swifquant daily price not yet implemented - need table schema")
        return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级行情数据

        TODO: 根据实际表结构调整 SQL
        """
        logger.warning("Swifquant minute price not yet implemented - need table schema")
        return pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取基本面数据

        TODO: 根据实际表结构调整 SQL
        """
        logger.warning("Swifquant fundamentals not yet implemented - need table schema")
        return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股

        TODO: 根据实际表结构调整 SQL
        """
        logger.warning("Swifquant index components not yet implemented - need table schema")
        return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历

        TODO: 根据实际表结构调整 SQL
        """
        logger.warning("Swifquant trade calendar not yet implemented - need table schema")
        return pd.DataFrame()

    def list_tables(self) -> pd.DataFrame:
        """列出数据库中的所有表（用于探索数据结构）"""
        sql = """
            SELECT
                TABLE_NAME as table_name,
                TABLE_COMMENT as table_comment
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME
        """
        return self._execute_query(sql)

    def get_table_schema(self, table_name: str) -> pd.DataFrame:
        """获取指定表的字段结构（用于了解表结构）"""
        sql = f"""
            SELECT
                COLUMN_NAME as column_name,
                DATA_TYPE as data_type,
                COLUMN_COMMENT as column_comment,
                IS_NULLABLE as is_nullable,
                COLUMN_DEFAULT as default_value
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """
        return self._execute_query(sql)

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT VERSION() as version"))
                version = result.scalar()
                logger.info(f"Swifquant connection test passed. MySQL version: {version}")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def raw_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行原始 SQL 查询（用于临时探索数据）"""
        return self._execute_query(sql, params)

from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional, Union

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import get_settings


class DatabaseManager:
    """数据库管理器

    负责与PostgreSQL数据库的交互，包括行情数据、因子数据的存储和查询
    """

    def __init__(self):
        self.settings = get_settings()
        self.engine = create_engine(
            self.settings.database.url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("DatabaseManager initialized")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库会话（上下文管理器）"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def save_daily_price(self, df: pd.DataFrame) -> bool:
        """保存日频行情数据

        Args:
            df: DataFrame with columns [symbol, date, open, high, low, close, volume, ...]

        Returns:
            是否保存成功
        """
        if df.empty:
            logger.warning("Empty dataframe, nothing to save")
            return False

        try:
            df.to_sql(
                "daily_price",
                self.engine,
                if_exists="append",
                index=False,
                method="multi"
            )
            logger.info(f"Saved {len(df)} rows to daily_price")
            return True
        except Exception as e:
            logger.error(f"Failed to save daily price: {e}")
            return False

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """从数据库查询日频行情数据"""
        if isinstance(symbol, str):
            symbol = [symbol]

        symbols_str = ",".join([f"'{s}'" for s in symbol])
        field_str = ",".join(fields) if fields else "*"

        sql = f"""
            SELECT {field_str} FROM daily_price
            WHERE symbol IN ({symbols_str})
        """

        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date

        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_factor_data(self, df: pd.DataFrame, factor_name: str) -> bool:
        """保存因子数据

        Args:
            df: DataFrame with columns [symbol, date, factor_value]
            factor_name: 因子名称，用于表名
        """
        if df.empty:
            return False

        table_name = f"factor_{factor_name}"

        try:
            df.to_sql(
                table_name,
                self.engine,
                if_exists="append",
                index=False
            )
            logger.info(f"Saved {len(df)} rows to {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save factor data: {e}")
            return False

    def execute_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行原始SQL查询

        Args:
            sql: SQL语句
            params: 查询参数

        Returns:
            查询结果DataFrame
        """
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def create_tables(self):
        """创建基础表结构（如果不存在）"""
        create_daily_price_sql = """
        CREATE TABLE IF NOT EXISTS daily_price (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            open DECIMAL(12, 4),
            high DECIMAL(12, 4),
            low DECIMAL(12, 4),
            close DECIMAL(12, 4),
            volume BIGINT,
            amount DECIMAL(20, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_price_symbol ON daily_price(symbol);
        CREATE INDEX IF NOT EXISTS idx_daily_price_date ON daily_price(date);
        """

        with self.engine.connect() as conn:
            conn.execute(text(create_daily_price_sql))
            conn.commit()
            logger.info("Database tables created/verified")

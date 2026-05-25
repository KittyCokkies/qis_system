"""
Database Connection Management

Handles database engine, session management, and raw SQL execution.
"""

from contextlib import contextmanager
from typing import Generator, Optional

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import get_settings


class DatabaseConnection:
    """数据库连接管理器"""

    def __init__(self):
        self.settings = get_settings()
        self.engine = create_engine(
            self.settings.database.url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("DatabaseConnection initialized")

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

    def execute(self, sql: str, params: Optional[dict] = None):
        """执行原始SQL"""
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result

    def execute_query(self, sql: str, params: Optional[dict] = None):
        """执行查询SQL并返回DataFrame"""
        import pandas as pd
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def create_tables(self):
        """创建所有表（从schema.sql读取）"""
        from pathlib import Path

        schema_file = Path(__file__).parent.parent.parent / "database" / "schema.sql"
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return

        with open(schema_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Split and execute statements
        statements = [s.strip() for s in sql_content.split(';') if s.strip()]

        with self.engine.connect() as conn:
            for stmt in statements:
                if stmt and not stmt.startswith('--'):
                    try:
                        conn.execute(text(stmt))
                    except Exception as e:
                        logger.warning(f"Statement failed (may already exist): {e}")
            conn.commit()

        logger.info("Database tables created")

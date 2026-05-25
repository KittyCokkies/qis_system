"""
数据库连接管理模块

提供数据库引擎、会话管理和原始SQL执行功能
支持PostgreSQL数据库连接池配置
"""

from contextlib import contextmanager
from typing import Generator, Optional

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import get_settings


class DatabaseConnection:
    """数据库连接管理器

    负责管理SQLAlchemy引擎和会话，提供数据库操作的基础功能

    Attributes:
        engine: SQLAlchemy数据库引擎
        SessionLocal: 会话工厂
        settings: 应用配置对象

    Example:
        >>> db = DatabaseConnection()
        >>> with db.get_session() as session:
        ...     result = session.execute("SELECT * FROM assets")
    """

    def __init__(self):
        """初始化数据库连接

        从配置中读取数据库URL，创建连接池
        """
        self.settings = get_settings()
        self.engine = create_engine(
            self.settings.database.url,
            pool_size=10,              # 连接池大小
            max_overflow=20,           # 最大溢出连接数
            pool_pre_ping=True,        # 连接前ping检测
            echo=False,                # 不输出SQL日志
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("DatabaseConnection initialized")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库会话（上下文管理器）

        使用上下文管理器自动处理会话的提交和回滚

        Yields:
            Session: SQLAlchemy会话对象

        Example:
            >>> with db.get_session() as session:
            ...     session.add(obj)
            ...     # 自动提交
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()          # 正常完成时提交
        except Exception as e:
            session.rollback()        # 异常时回滚
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()           # 确保会话关闭

    def execute(self, sql: str, params: Optional[dict] = None):
        """执行原始SQL语句

        用于执行INSERT/UPDATE/DELETE等数据修改操作

        Args:
            sql: SQL语句字符串
            params: SQL参数字典，用于防止SQL注入

        Returns:
            ResultProxy: SQL执行结果

        Example:
            >>> db.execute("INSERT INTO assets (symbol) VALUES (:symbol)",
            ...            {"symbol": "IF2401"})
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result

    def execute_query(self, sql: str, params: Optional[dict] = None):
        """执行查询SQL并返回DataFrame

        用于执行SELECT查询，自动将结果转换为pandas DataFrame

        Args:
            sql: SQL查询语句
            params: SQL参数字典

        Returns:
            pd.DataFrame: 查询结果的数据框

        Example:
            >>> df = db.execute_query("SELECT * FROM prices WHERE date > :date",
            ...                         {"date": "2024-01-01"})
        """
        import pandas as pd
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def create_tables(self):
        """创建所有表（从schema.sql读取）

        读取database/schema.sql文件，执行其中的CREATE TABLE语句
        如果表已存在则跳过（使用IF NOT EXISTS）
        """
        from pathlib import Path

        schema_file = Path(__file__).parent.parent.parent / "database" / "schema.sql"
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return

        with open(schema_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # 分割并执行语句
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

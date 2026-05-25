"""
数据库表初始化脚本

用法:
    python database/init_tables.py
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from sqlalchemy import create_engine, text
from config import get_settings


def init_database():
    """初始化数据库表结构"""
    settings = get_settings()

    logger.info("Connecting to PostgreSQL database...")
    engine = create_engine(
        settings.database.url,
        pool_size=5,
        max_overflow=10
    )

    # 读取SQL文件
    schema_file = Path(__file__).parent / "schema.sql"

    if not schema_file.exists():
        logger.error(f"Schema file not found: {schema_file}")
        return False

    with open(schema_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # 分割SQL语句并执行
    statements = [s.strip() for s in sql_content.split(';') if s.strip()]

    with engine.connect() as conn:
        with conn.begin():
            for statement in statements:
                if not statement or statement.startswith('--'):
                    continue
                try:
                    conn.execute(text(statement + ';'))
                    logger.debug(f"Executed: {statement[:50]}...")
                except Exception as e:
                    # 忽略已存在的错误
                    if "already exists" in str(e) or "duplicate" in str(e).lower():
                        logger.debug(f"Skipping (already exists): {statement[:50]}...")
                    else:
                        logger.warning(f"Error executing SQL: {e}")
                        logger.warning(f"SQL: {statement[:100]}...")

    logger.info("Database tables initialized successfully!")
    return True


def verify_tables():
    """验证表是否创建成功"""
    settings = get_settings()
    engine = create_engine(settings.database.url)

    expected_tables = [
        'assets',
        'trade_calendar',
        'prices_stock',
        'prices_future',
        'prices_future_continuous',
        'prices_index',
        'factors_asset',
        'factors_commodity',
        'fx_rates',
        'macro_indicators',
        'market_regime',
        'strategies',
        'strategy_nav',
        'target_positions',
        'actual_positions',
        'trades',
        'rollover_executions',
        'index_components',
        'industry_classification',
    ]

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ))
        existing_tables = [row[0] for row in result]

    logger.info("=" * 60)
    logger.info("Table Verification")
    logger.info("=" * 60)

    for table in expected_tables:
        status = "✓" if table in existing_tables else "✗"
        logger.info(f"{status} {table}")

    missing = set(expected_tables) - set(existing_tables)
    if missing:
        logger.warning(f"Missing tables: {missing}")
        return False

    logger.info("All tables verified successfully!")
    return True


if __name__ == "__main__":
    logger.add(sys.stderr, format="{time} | {level} | {message}")

    if init_database():
        verify_tables()
    else:
        logger.error("Failed to initialize database")
        sys.exit(1)

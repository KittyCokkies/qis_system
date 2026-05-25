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


def parse_sql_file(sql_content: str) -> tuple:
    """解析SQL文件，分离不同类型的语句

    Returns:
        (create_table_stmts, create_view_stmts, function_stmts,
         create_index_stmts, trigger_stmts, comment_stmts, other_stmts)
    """
    # 按行分割并处理
    lines = sql_content.split('\n')

    create_table_stmts = []
    create_index_stmts = []
    create_view_stmts = []
    function_stmts = []
    trigger_stmts = []
    comment_stmts = []
    other_stmts = []

    current_stmt = []
    in_function = False

    for line in lines:
        stripped = line.strip()

        # 跳过纯注释行，但保留当前语句中的注释
        if not stripped or (stripped.startswith('--') and not current_stmt):
            continue

        # 检测函数/触发器开始
        if 'CREATE OR REPLACE FUNCTION' in stripped.upper():
            in_function = True

        current_stmt.append(line)

        # 语句结束（分号）
        if stripped.endswith(';'):
            stmt = '\n'.join(current_stmt).strip()
            current_stmt = []

            if in_function:
                if 'LANGUAGE' in stmt.upper() and '$$' not in stmt:
                    in_function = False
                    function_stmts.append(stmt)
                continue

            # 分类语句
            upper_stmt = stmt.upper()
            if 'CREATE TABLE' in upper_stmt:
                create_table_stmts.append(stmt)
            elif 'CREATE INDEX' in upper_stmt:
                create_index_stmts.append(stmt)
            elif 'CREATE VIEW' in upper_stmt or 'CREATE OR REPLACE VIEW' in upper_stmt:
                create_view_stmts.append(stmt)
            elif 'CREATE TRIGGER' in upper_stmt:
                trigger_stmts.append(stmt)
            elif 'COMMENT ON' in upper_stmt:
                comment_stmts.append(stmt)
            else:
                other_stmts.append(stmt)

    # 执行顺序：表 -> 视图 -> 函数 -> 索引 -> 触发器 -> 注释
    return (
        create_table_stmts,
        create_view_stmts,
        function_stmts,
        create_index_stmts,
        trigger_stmts,
        comment_stmts,
        other_stmts
    )


def execute_statements(conn, stmts: list, stmt_type: str) -> int:
    """执行一组SQL语句

    Returns:
        成功执行的语句数
    """
    success_count = 0
    for stmt in stmts:
        if not stmt.strip():
            continue
        try:
            conn.execute(text(stmt))
            success_count += 1
            logger.debug(f"Executed {stmt_type}: {stmt[:60]}...")
        except Exception as e:
            error_msg = str(e).lower()
            # 忽略已存在的错误
            if any(x in error_msg for x in ['already exists', 'duplicate', 'exist']):
                logger.debug(f"Skipping (already exists): {stmt[:60]}...")
                success_count += 1  # 算作成功
            else:
                logger.warning(f"Error executing {stmt_type}: {e}")
                logger.warning(f"SQL: {stmt[:150]}...")
    return success_count


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

    # 解析SQL语句
    tables, views, functions, indexes, triggers, comments, others = parse_sql_file(sql_content)

    logger.info(f"Parsed SQL: {len(tables)} tables, {len(views)} views, "
                f"{len(functions)} functions, {len(indexes)} indexes, "
                f"{len(triggers)} triggers, {len(comments)} comments")

    with engine.connect() as conn:
        with conn.begin():
            # 1. 创建表（最先执行）
            logger.info("Creating tables...")
            execute_statements(conn, tables, "TABLE")

            # 2. 创建视图
            if views:
                logger.info("Creating views...")
                execute_statements(conn, views, "VIEW")

            # 3. 创建函数
            if functions:
                logger.info("Creating functions...")
                execute_statements(conn, functions, "FUNCTION")

            # 4. 创建索引
            if indexes:
                logger.info("Creating indexes...")
                execute_statements(conn, indexes, "INDEX")

            # 5. 创建触发器
            if triggers:
                logger.info("Creating triggers...")
                execute_statements(conn, triggers, "TRIGGER")

            # 6. 添加表注释
            if comments:
                logger.info("Adding table comments...")
                execute_statements(conn, comments, "COMMENT")

            # 7. 其他语句
            if others:
                logger.info("Executing other statements...")
                execute_statements(conn, others, "OTHER")

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
        'hedge_instrument_mapping',
        'synthetic_index_series',
        'strategy_index_series',
        'hedge_comparison',
        'strategy_hedge_config',
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

    success_count = 0
    for table in expected_tables:
        if table in existing_tables:
            logger.info(f"✓ {table}")
            success_count += 1
        else:
            logger.warning(f"✗ {table}")

    logger.info("=" * 60)
    logger.info(f"Result: {success_count}/{len(expected_tables)} tables created")
    logger.info("=" * 60)

    if success_count == len(expected_tables):
        logger.info("All tables verified successfully!")
        return True
    else:
        missing = set(expected_tables) - set(existing_tables)
        logger.warning(f"Missing tables: {missing}")
        return False


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")

    if init_database():
        verify_tables()
    else:
        logger.error("Failed to initialize database")
        sys.exit(1)

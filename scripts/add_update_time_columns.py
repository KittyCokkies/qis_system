#!/usr/bin/env python3
"""
为数据库表添加 update_time 字段
用于记录数据同步时间
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def add_update_time_columns():
    """为各表添加 update_time 字段"""
    db = DatabaseManager()

    # 需要添加 update_time 字段的表
    tables = [
        'prices_stock',
        'prices_index',
        'fx_rates',
        'macro_indicators',
    ]

    logger.info("开始为数据库表添加 update_time 字段...")

    for table in tables:
        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    # 检查字段是否已存在
                    check_sql = f"""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = '{table}'
                        AND column_name = 'update_time'
                    """
                    result = conn.execute(text(check_sql))
                    if result.fetchone():
                        logger.info(f"[{table}] update_time 字段已存在，跳过")
                    else:
                        # 添加字段
                        alter_sql = f"""
                            ALTER TABLE {table}
                            ADD COLUMN update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        """
                        conn.execute(text(alter_sql))
                        logger.info(f"[{table}] 成功添加 update_time 字段")
        except Exception as e:
            logger.error(f"[{table}] 添加字段失败: {e}")

    logger.info("数据库表 update_time 字段添加完成")


if __name__ == "__main__":
    add_update_time_columns()

#!/usr/bin/env python3
"""
修正assets表结构
1. 删除created_at字段，只保留updated_at并重命名为update_time
2. 使用INSERT ON CONFLICT DO NOTHING避免重复更新
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def fix_assets_table():
    """修正assets表结构"""
    db = DatabaseManager()

    logger.info("[assets] 开始修正表结构...")
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 1. 删除created_at列
                conn.execute(text("ALTER TABLE assets DROP COLUMN IF EXISTS created_at"))
                logger.info("[assets] 已删除created_at列")

                # 2. 重命名updated_at为update_time
                conn.execute(text("ALTER TABLE assets RENAME COLUMN updated_at TO update_time"))
                logger.info("[assets] 已将updated_at重命名为update_time")

                # 3. 修改约束，使用ON CONFLICT时不更新update_time
                # 这样可以避免每次同步都更新时间
                # 如果需要更新时间，可以手动触发或在价格数据更新时触发

        logger.info("[assets] 表结构修正完成")
    except Exception as e:
        logger.error(f"[assets] 修正失败: {e}")


if __name__ == "__main__":
    fix_assets_table()

#!/usr/bin/env python3
"""
重构 fx_rates 表结构
1. 删除现有数据
2. 去掉 id、from_currency、to_currency 字段
3. 使用 symbol 字段存储万得代码/彭博代码
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def restructure_fx_table():
    """重构 fx_rates 表"""
    db = DatabaseManager()

    logger.info("[fx_rates] 开始重构表结构...")

    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 1. 删除现有数据
                result = conn.execute(text("SELECT COUNT(*) FROM fx_rates"))
                count = result.scalar()
                conn.execute(text("DELETE FROM fx_rates"))
                logger.info(f"[fx_rates] 已删除 {count} 条现有数据")

                # 2. 删除旧表
                conn.execute(text("DROP TABLE IF EXISTS fx_rates"))
                logger.info("[fx_rates] 已删除旧表")

                # 3. 创建新表结构
                conn.execute(text("""
                    CREATE TABLE fx_rates (
                        symbol VARCHAR(50) NOT NULL,      -- 万得代码/彭博代码，如 M0000185, EURCNH L160 Curncy
                        date DATE NOT NULL,               -- 日期
                        spot_rate DECIMAL(12, 6),         -- 即期汇率
                        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (symbol, date),
                        FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
                    )
                """))
                logger.info("[fx_rates] 新表创建成功")

                # 4. 创建索引
                conn.execute(text("""
                    CREATE INDEX idx_fx_rates_symbol_date ON fx_rates(symbol, date DESC)
                """))
                conn.execute(text("""
                    CREATE INDEX idx_fx_rates_date ON fx_rates(date)
                """))
                logger.info("[fx_rates] 索引创建成功")

        logger.info("[fx_rates] 表结构重构完成")
        logger.info("  新结构: symbol + date + spot_rate + update_time")

    except Exception as e:
        logger.error(f"[fx_rates] 重构失败: {e}")


if __name__ == "__main__":
    restructure_fx_table()

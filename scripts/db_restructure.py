#!/usr/bin/env python3
"""
数据库结构调整脚本
1. 创建 prices_etf 表
2. 清理 prices_stock 所有数据
3. 删除 macro_indicators 的 id 字段
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def create_prices_etf_table(db: DatabaseManager):
    """创建 prices_etf 表"""
    logger.info("[prices_etf] 创建ETF价格表...")
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS prices_etf (
                        symbol VARCHAR(20) NOT NULL,
                        date DATE NOT NULL,
                        open DECIMAL(12, 4),
                        high DECIMAL(12, 4),
                        low DECIMAL(12, 4),
                        close DECIMAL(12, 4),
                        volume BIGINT,
                        amount DECIMAL(20, 4),
                        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (symbol, date),
                        FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
                    )
                """))

                # 创建索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_prices_etf_symbol_date
                    ON prices_etf(symbol, date DESC)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_prices_etf_date
                    ON prices_etf(date)
                """))

                logger.info("[prices_etf] 表创建成功")
    except Exception as e:
        logger.error(f"[prices_etf] 创建失败: {e}")


def clear_prices_stock(db: DatabaseManager):
    """清理 prices_stock 所有数据"""
    logger.info("[prices_stock] 清理所有数据...")
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                result = conn.execute(text("SELECT COUNT(*) FROM prices_stock"))
                count = result.scalar()

                conn.execute(text("DELETE FROM prices_stock"))
                logger.info(f"[prices_stock] 已删除 {count} 条记录")
    except Exception as e:
        logger.error(f"[prices_stock] 清理失败: {e}")


def remove_macro_indicators_id(db: DatabaseManager):
    """删除 macro_indicators 的 id 字段"""
    logger.info("[macro_indicators] 删除id字段...")
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 检查id字段是否存在
                result = conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'macro_indicators' AND column_name = 'id'
                """))
                if not result.fetchone():
                    logger.info("[macro_indicators] id字段不存在，跳过")
                    return

                # 删除主键约束
                conn.execute(text("""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'macro_indicators_pkey'
                            AND conrelid = 'macro_indicators'::regclass
                        ) THEN
                            ALTER TABLE macro_indicators DROP CONSTRAINT macro_indicators_pkey;
                        END IF;
                    END $$;
                """))

                # 删除id列
                conn.execute(text("ALTER TABLE macro_indicators DROP COLUMN IF EXISTS id"))

                # 设置新的主键
                conn.execute(text("""
                    ALTER TABLE macro_indicators
                    ADD CONSTRAINT macro_indicators_pkey PRIMARY KEY (indicator_code, date)
                """))

                logger.info("[macro_indicators] 成功删除id字段")
    except Exception as e:
        logger.error(f"[macro_indicators] 删除失败: {e}")


def main():
    db = DatabaseManager()

    logger.info("=" * 80)
    logger.info("数据库结构调整")
    logger.info("=" * 80)

    create_prices_etf_table(db)
    clear_prices_stock(db)
    remove_macro_indicators_id(db)

    logger.info("=" * 80)
    logger.info("操作完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

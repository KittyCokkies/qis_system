#!/usr/bin/env python3
"""
修正数据库问题：
1. 删除 prices_stock 和 prices_index 表的 id 字段
2. 修正 assets 表中 ETF 和场外基金的分类
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def remove_id_column(db: DatabaseManager, table_name: str):
    """删除表的 id 字段，使用 symbol + date 作为主键"""
    logger.info(f"[{table_name}] 开始删除 id 字段...")

    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 检查 id 字段是否存在
                result = conn.execute(text(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}' AND column_name = 'id'
                """))
                if not result.fetchone():
                    logger.info(f"[{table_name}] id 字段不存在，跳过")
                    return

                # 删除 id 列（ PostgreSQL 需要先删除约束）
                # 1. 删除主键约束
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = '{table_name}_pkey'
                            AND conrelid = '{table_name}'::regclass
                        ) THEN
                            ALTER TABLE {table_name} DROP CONSTRAINT {table_name}_pkey;
                        END IF;
                    END $$;
                """))

                # 2. 删除 id 列
                conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS id"))

                # 3. 添加新的主键约束 (symbol, date)
                conn.execute(text(f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {table_name}_pkey PRIMARY KEY (symbol, date)
                """))

                logger.info(f"[{table_name}] 成功删除 id 字段，设置 (symbol, date) 为主键")
    except Exception as e:
        logger.error(f"[{table_name}] 删除 id 字段失败: {e}")


def fix_asset_classification(db: DatabaseManager):
    """修正 assets 表中 ETF 和场外基金的分类"""
    logger.info("开始修正 assets 表分类...")

    # ETF 列表（来自 wind_config.py）
    etf_list = [
        '0JGN.L', '588000.SH', 'INDA.BAT', '159732.SZ', '159755.SZ',
        '159852.SZ', '159985.SZ', '159992.SZ', '159995.SZ', '511380.SH',
        '512400.SH', '512660.SH', '512890.SH', '515790.SH', '515980.SH',
        '562500.SH', '159915.SZ'
    ]

    # 场外基金列表
    fund_list = ['007994.OF', '110026.OF', '501018.SH']

    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 更新 ETF 分类
                for symbol in etf_list:
                    result = conn.execute(
                        text("UPDATE assets SET asset_class = 'etf' WHERE symbol = :symbol"),
                        {'symbol': symbol}
                    )
                    if result.rowcount > 0:
                        logger.info(f"  {symbol} -> etf")

                # 先修改约束以允许 'fund' 类型
                conn.execute(text("""
                    ALTER TABLE assets DROP CONSTRAINT IF EXISTS chk_asset_class;
                """))
                conn.execute(text("""
                    ALTER TABLE assets ADD CONSTRAINT chk_asset_class
                    CHECK (asset_class IN ('stock', 'future', 'index', 'etf', 'bond', 'option', 'commodity', 'fund'));
                """))
                logger.info("  已更新 assets 表约束，添加 'fund' 类型")

                # 更新场外基金分类
                for symbol in fund_list:
                    result = conn.execute(
                        text("UPDATE assets SET asset_class = 'fund' WHERE symbol = :symbol"),
                        {'symbol': symbol}
                    )
                    if result.rowcount > 0:
                        logger.info(f"  {symbol} -> fund")

                logger.info("assets 表分类修正完成")
    except Exception as e:
        logger.error(f"修正 assets 分类失败: {e}")


def migrate_index_data(db: DatabaseManager):
    """
    将 prices_stock 中的指数数据迁移到 prices_index
    根据 wind_config.py，dividend_yield 类的指数应该只在 macro_indicators 中
    而 underlying_index 类的应该在 prices_index 中
    """
    logger.info("检查 prices_stock 中是否有应属于 prices_index 的数据...")

    # 这些是在 wind_config 中配置为 underlying_index 的标的
    index_symbols = [
        '000300.SH', '000688.SH', '000905.SH',  # 已在 prices_index
    ]

    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 检查 prices_stock 中是否有这些指数数据
                for symbol in index_symbols:
                    result = conn.execute(
                        text("SELECT COUNT(*) FROM prices_stock WHERE symbol = :symbol"),
                        {'symbol': symbol}
                    )
                    count = result.scalar()
                    if count > 0:
                        logger.info(f"  {symbol}: prices_stock 中有 {count} 条数据")
                        # 迁移到 prices_index
                        conn.execute(text(f"""
                            INSERT INTO prices_index (symbol, date, close, update_time)
                            SELECT symbol, date, close, update_time
                            FROM prices_stock
                            WHERE symbol = '{symbol}'
                            ON CONFLICT (symbol, date) DO UPDATE SET
                                close = EXCLUDED.close,
                                update_time = EXCLUDED.update_time
                        """))
                        # 从 prices_stock 删除
                        conn.execute(
                            text("DELETE FROM prices_stock WHERE symbol = :symbol"),
                            {'symbol': symbol}
                        )
                        logger.info(f"  -> 已迁移到 prices_index")
    except Exception as e:
        logger.error(f"数据迁移失败: {e}")


def main():
    db = DatabaseManager()

    logger.info("="*80)
    logger.info("开始修正数据库问题")
    logger.info("="*80)

    # 1. 删除 id 字段
    remove_id_column(db, 'prices_stock')
    remove_id_column(db, 'prices_index')

    # 2. 修正 assets 分类
    fix_asset_classification(db)

    # 3. 迁移数据（如有需要）
    migrate_index_data(db)

    logger.info("="*80)
    logger.info("数据库修正完成")
    logger.info("="*80)


if __name__ == "__main__":
    main()

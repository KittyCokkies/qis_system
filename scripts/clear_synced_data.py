#!/usr/bin/env python3
"""
清理同步数据脚本
删除万得同步和彭博同步脚本已同步到数据库的数据
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def clear_wind_data():
    """清理万得同步的数据"""
    db = DatabaseManager()

    # 万得数据同步的表
    wind_tables = {
        'fx_rates': '外汇汇率数据',
        'macro_indicators': '宏观指标数据',
        'prices_stock': 'ETF/股票价格数据',
        'prices_index': '指数价格数据',
    }

    logger.info("="*80)
    logger.info("开始清理万得同步数据")
    logger.info("="*80)

    total_deleted = 0
    for table, desc in wind_tables.items():
        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    # 获取删除前的记录数
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count_before = count_result.scalar()

                    # 删除所有数据
                    conn.execute(text(f"DELETE FROM {table}"))

                    logger.info(f"[{table}] {desc}: 已删除 {count_before} 条记录")
                    total_deleted += count_before
        except Exception as e:
            logger.error(f"[{table}] 清理失败: {e}")

    logger.info(f"万得数据清理完成，共删除 {total_deleted} 条记录")
    return total_deleted


def clear_bloomberg_data():
    """清理彭博同步的数据"""
    db = DatabaseManager()

    logger.info("="*80)
    logger.info("开始清理彭博同步数据")
    logger.info("="*80)

    total_deleted = 0

    # 清理 prices_index 中的彭博数据（BLOOMBERG交易所）
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 获取删除前的记录数
                count_result = conn.execute(text("""
                    SELECT COUNT(*) FROM prices_index p
                    JOIN assets a ON p.symbol = a.symbol
                    WHERE a.exchange = 'BLOOMBERG'
                """))
                count_before = count_result.scalar()

                # 删除彭博的指数数据
                conn.execute(text("""
                    DELETE FROM prices_index p
                    WHERE EXISTS (
                        SELECT 1 FROM assets a
                        WHERE a.symbol = p.symbol
                        AND a.exchange = 'BLOOMBERG'
                    )
                """))

                logger.info(f"[prices_index] 彭博指数数据: 已删除 {count_before} 条记录")
                total_deleted += count_before
    except Exception as e:
        logger.error(f"[prices_index] 彭博数据清理失败: {e}")

    # 清理 fx_rates 中的彭博数据（通过symbol关联）
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 彭博外汇代码通常包含 Curncy
                count_result = conn.execute(text("""
                    SELECT COUNT(*) FROM fx_rates
                    WHERE from_currency IN ('CNH', 'USD')
                    AND to_currency IN ('USD', 'CNY', 'CNH')
                """))
                count_before = count_result.scalar()

                # 删除这些外汇记录
                conn.execute(text("""
                    DELETE FROM fx_rates
                    WHERE from_currency IN ('CNH', 'USD')
                    AND to_currency IN ('USD', 'CNY', 'CNH')
                """))

                logger.info(f"[fx_rates] 彭博外汇数据: 已删除 {count_before} 条记录")
                total_deleted += count_before
    except Exception as e:
        logger.error(f"[fx_rates] 彭博数据清理失败: {e}")

    # 清理 prices_future 中的DMA数据
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                count_result = conn.execute(text("""
                    SELECT COUNT(*) FROM prices_future WHERE underlying = 'DMA'
                """))
                count_before = count_result.scalar()

                conn.execute(text("""
                    DELETE FROM prices_future WHERE underlying = 'DMA'
                """))

                logger.info(f"[prices_future] DMA期货数据: 已删除 {count_before} 条记录")
                total_deleted += count_before
    except Exception as e:
        logger.error(f"[prices_future] DMA数据清理失败: {e}")

    logger.info(f"彭博数据清理完成，共删除 {total_deleted} 条记录")
    return total_deleted


def clear_all_synced_data():
    """清理所有同步数据"""
    logger.info("\n" + "="*80)
    logger.info("开始清理所有同步数据")
    logger.info("="*80 + "\n")

    wind_count = clear_wind_data()
    bloomberg_count = clear_bloomberg_data()

    logger.info("\n" + "="*80)
    logger.info("数据清理完成汇总")
    logger.info("="*80)
    logger.info(f"万得数据: {wind_count} 条")
    logger.info(f"彭博数据: {bloomberg_count} 条")
    logger.info(f"总计删除: {wind_count + bloomberg_count} 条")
    logger.info("="*80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='清理同步数据')
    parser.add_argument('--wind-only', action='store_true', help='只清理万得数据')
    parser.add_argument('--bloomberg-only', action='store_true', help='只清理彭博数据')
    parser.add_argument('--yes', action='store_true', help='确认执行，不提示')

    args = parser.parse_args()

    if not args.yes:
        confirm = input("确认要删除所有同步数据吗？此操作不可恢复！(yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("操作已取消")
            return

    if args.wind_only:
        clear_wind_data()
    elif args.bloomberg_only:
        clear_bloomberg_data()
    else:
        clear_all_synced_data()


if __name__ == "__main__":
    main()

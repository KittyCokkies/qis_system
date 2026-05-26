#!/usr/bin/env python3
"""
更新合约详细信息

从通联 futu 表获取合约乘数、tick size、上市/退市日期等信息，
更新到本地 assets 表
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from loguru import logger
import pandas as pd

from data.tonglian_source import TonglianSource
from data.database import DatabaseManager


def update_contract_details(underlying: str = None, dry_run: bool = False):
    """更新合约详细信息

    Args:
        underlying: 品种代码，如 'IF'。None 表示更新所有期货合约
        dry_run: 是否只打印不执行
    """
    source = TonglianSource()
    db = DatabaseManager()

    # 获取需要更新的合约
    if underlying:
        underlyings = [underlying]
    else:
        # 从现有 assets 表中获取所有期货品种
        df = db.execute_query(
            "SELECT DISTINCT underlying FROM assets WHERE asset_class = 'future'"
        )
        underlyings = df['underlying'].tolist() if not df.empty else []

    logger.info(f"需要更新 {len(underlyings)} 个品种的合约详情")

    total_updated = 0
    total_matched = 0

    for ul in underlyings:
        logger.info(f"处理品种: {ul}")

        # 从 futu 表获取合约详情
        details = source.get_contract_details(ul)

        if details.empty:
            logger.warning(f"  在 futu 表未找到 {ul} 的合约详情")
            continue

        matched = 0
        for _, row in details.iterrows():
            symbol = row['symbol']

            # 转换日期
            list_date = row.get('list_date')
            last_trade_date = row.get('last_trade_date')

            if pd.notna(list_date) and hasattr(list_date, 'date'):
                list_date = list_date.date()
            if pd.notna(last_trade_date) and hasattr(last_trade_date, 'date'):
                last_trade_date = last_trade_date.date()

            if dry_run:
                logger.info(f"  [DRY RUN] {symbol}: "
                           f"乘数={row.get('multiplier')}, "
                           f"tick={row.get('tick_size')}, "
                           f"上市={list_date}, "
                           f"到期={last_trade_date}")
                matched += 1
                continue

            try:
                db.execute("""
                    UPDATE assets
                    SET contract_month = :contract_month,
                        list_date = :list_date,
                        delist_date = :delist_date,
                        multiplier = :multiplier,
                        tick_size = :tick_size,
                        exchange = :exchange,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = :symbol
                """, {
                    'symbol': symbol,
                    'contract_month': row.get('contract_month'),
                    'list_date': list_date,
                    'delist_date': last_trade_date,
                    'multiplier': row.get('multiplier'),
                    'tick_size': row.get('tick_size'),
                    'exchange': row.get('exchange', 'CFFEX')
                })
                matched += 1
            except Exception as e:
                logger.error(f"  更新 {symbol} 失败: {e}")

        logger.info(f"  匹配并更新 {matched} 个合约")
        total_matched += matched

    logger.info(f"完成: 共更新 {total_matched} 个合约的详细信息")
    return total_matched


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='更新期货合约详细信息')
    parser.add_argument('--underlying', type=str, help='品种代码 (如: IF, RB)')
    parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')

    args = parser.parse_args()

    update_contract_details(
        underlying=args.underlying,
        dry_run=args.dry_run
    )

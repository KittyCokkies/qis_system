#!/usr/bin/env python3
"""
通联数据完整同步脚本

自动导入合约信息并同步价格数据
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date
from loguru import logger
from tqdm import tqdm

from data.tonglian_source import TonglianSource
from data.sync.tonglian_sync import TonglianSync
from data.database import DatabaseManager


def import_contracts(underlying: str, source: TonglianSource, db: DatabaseManager) -> int:
    """导入合约到 assets 表"""
    contracts = source.get_future_contracts(underlying, start_date=datetime(2024, 1, 1))
    count = 0

    for _, row in contracts.iterrows():
        try:
            db.execute('''
                INSERT INTO assets (symbol, underlying, name, asset_class, exchange, is_active)
                VALUES (:symbol, :underlying, :name, :asset_class, :exchange, :is_active)
                ON CONFLICT (symbol) DO NOTHING
            ''', {
                'symbol': row['symbol'],
                'underlying': row['underlying'],
                'name': row['symbol'],
                'asset_class': 'future',
                'exchange': row.get('exchange', 'CFFEX'),
                'is_active': True
            })
            count += 1
        except Exception as e:
            logger.warning(f"导入 {row['symbol']} 失败: {e}")

    return count


def sync_tonglian_data(start_date: date, end_date: date, underlyings: list = None):
    """
    同步通联数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
        underlyings: 品种列表，None表示全部
    """
    logger.info("=" * 60)
    logger.info("通联数据同步")
    logger.info(f"日期范围: {start_date} 至 {end_date}")
    logger.info("=" * 60)

    source = TonglianSource()
    sync = TonglianSync()
    db = DatabaseManager()

    # 获取配置
    configs = sync.get_active_configs()
    if underlyings:
        configs = [(u, c) for u, c in configs if u in underlyings]

    logger.info(f"需要同步 {len(configs)} 个品种")

    # 步骤1: 导入合约信息
    logger.info("步骤 1: 导入合约信息...")
    total_contracts = 0
    for underlying, _ in tqdm(configs, desc="导入合约"):
        count = import_contracts(underlying, source, db)
        total_contracts += count
    logger.info(f"导入完成: {total_contracts} 个合约")

    # 步骤2: 同步价格数据
    logger.info("步骤 2: 同步价格数据...")
    from datetime import timedelta

    total_records = 0
    current = start_date
    while current <= end_date:
        for underlying, _ in configs:
            try:
                records = sync.sync_daily_data(underlying, current)
                total_records += records
            except Exception as e:
                logger.error(f"同步 {underlying} {current} 失败: {e}")
        current += timedelta(days=1)

    logger.info(f"同步完成: {total_records} 条记录")
    return total_records


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='同步通联期货数据')
    parser.add_argument('--start', type=str, default='2024-12-01', help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2024-12-20', help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--underlyings', type=str, help='品种列表，逗号分隔 (如: IF,IC,IM)')

    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    underlyings = None
    if args.underlyings:
        underlyings = [u.strip() for u in args.underlyings.split(',')]

    sync_tonglian_data(start, end, underlyings)

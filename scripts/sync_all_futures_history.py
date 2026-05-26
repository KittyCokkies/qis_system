#!/usr/bin/env python3
"""
同步所有期货历史数据

从各品种上市日开始同步到指定日期（默认2026-05-25）
使用配置文件中的start_date作为各品种的起始日期
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date, timedelta
from loguru import logger
from tqdm import tqdm
import pandas as pd

from data.tonglian_source import TonglianSource
from data.sync.tonglian_sync import TonglianSync
from data.database import DatabaseManager
from data.config.loader import AssetConfigLoader


def import_contracts_with_details(underlying: str, source: TonglianSource, db: DatabaseManager) -> int:
    """导入合约到assets表，包含详细信息，不限制日期范围"""
    # 从futu表获取合约详细信息（乘数、tick size等）
    details = source.get_contract_details(underlying)

    if details.empty:
        logger.warning(f"在futu表未找到 {underlying} 的合约详情")
        return 0

    details_dict = details.set_index('symbol').to_dict('index')

    count = 0
    for symbol, detail in details_dict.items():
        try:
            # 转换日期
            list_date = detail.get('list_date')
            last_trade_date = detail.get('last_trade_date')

            if pd.notna(list_date) and hasattr(list_date, 'date'):
                list_date = list_date.date()
            if pd.notna(last_trade_date) and hasattr(last_trade_date, 'date'):
                last_trade_date = last_trade_date.date()

            db.execute('''
                INSERT INTO assets
                (symbol, underlying, name, asset_class, exchange, is_active,
                 contract_month, list_date, delist_date, multiplier, tick_size)
                VALUES (:symbol, :underlying, :name, :asset_class, :exchange, :is_active,
                        :contract_month, :list_date, :delist_date, :multiplier, :tick_size)
                ON CONFLICT (symbol) DO UPDATE SET
                    contract_month = EXCLUDED.contract_month,
                    list_date = EXCLUDED.list_date,
                    delist_date = EXCLUDED.delist_date,
                    multiplier = EXCLUDED.multiplier,
                    tick_size = EXCLUDED.tick_size,
                    exchange = EXCLUDED.exchange,
                    updated_at = CURRENT_TIMESTAMP
            ''', {
                'symbol': symbol,
                'underlying': underlying,
                'name': symbol,
                'asset_class': 'future',
                'exchange': detail.get('exchange', 'CFFEX'),
                'is_active': True,
                'contract_month': detail.get('contract_month'),
                'list_date': list_date,
                'delist_date': last_trade_date,
                'multiplier': detail.get('multiplier'),
                'tick_size': detail.get('tick_size')
            })
            count += 1
        except Exception as e:
            logger.warning(f"导入 {symbol} 失败: {e}")

    logger.info(f"导入 {underlying}: {count} 个合约")
    return count


def sync_future_history(underlying: str, start_date: date, end_date: date, source: TonglianSource, sync: TonglianSync) -> int:
    """同步单个品种的历史数据"""
    total_records = 0
    current = start_date

    # 使用月份为单位的进度条
    total_days = (end_date - start_date).days + 1

    with tqdm(total=total_days, desc=f"{underlying} 数据同步", leave=False) as pbar:
        while current <= end_date:
            try:
                records = sync.sync_daily_data(underlying, current)
                total_records += records
            except Exception as e:
                logger.error(f"同步 {underlying} {current} 失败: {e}")

            current += timedelta(days=1)
            pbar.update(1)

    return total_records


def sync_all_futures_history(end_date: date = None):
    """
    同步所有期货品种的历史数据

    Args:
        end_date: 结束日期，默认2026-05-25
    """
    if end_date is None:
        end_date = date(2026, 5, 25)

    logger.info("=" * 80)
    logger.info("期货历史数据全量同步")
    logger.info(f"结束日期: {end_date}")
    logger.info("=" * 80)

    # 加载配置
    config_loader = AssetConfigLoader()
    config_loader.load()

    # 获取所有期货品种
    futures = config_loader.futures
    logger.info(f"配置文件中共有 {len(futures)} 个期货品种")

    source = TonglianSource()
    sync = TonglianSync()
    db = DatabaseManager()

    # 统计信息
    stats = []

    for underlying, future_config in futures.items():
        # 获取该品种的起始日期
        start_date = future_config.configs[0].start_date if future_config.configs else date(2010, 1, 1)
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        logger.info(f"\n{'='*60}")
        logger.info(f"处理品种: {underlying} ({future_config.name})")
        logger.info(f"数据范围: {start_date} 至 {end_date}")
        logger.info(f"{'='*60}")

        # 步骤1: 导入合约信息
        logger.info("步骤1: 导入合约信息...")
        contract_count = import_contracts_with_details(underlying, source, db)

        # 步骤2: 同步价格数据
        logger.info("步骤2: 同步价格数据...")
        record_count = sync_future_history(underlying, start_date, end_date, source, sync)

        stats.append({
            'underlying': underlying,
            'name': future_config.name,
            'start_date': start_date,
            'contract_count': contract_count,
            'record_count': record_count
        })

        logger.info(f"{underlying} 完成: {contract_count} 个合约, {record_count} 条价格记录")

    # 打印汇总
    logger.info("\n" + "=" * 80)
    logger.info("同步完成汇总")
    logger.info("=" * 80)

    total_contracts = sum(s['contract_count'] for s in stats)
    total_records = sum(s['record_count'] for s in stats)

    logger.info(f"{'品种':<8} {'名称':<12} {'起始日期':<12} {'合约数':>8} {'记录数':>10}")
    logger.info("-" * 80)
    for s in stats:
        logger.info(f"{s['underlying']:<8} {s['name']:<12} {str(s['start_date']):<12} {s['contract_count']:>8} {s['record_count']:>10}")
    logger.info("-" * 80)
    logger.info(f"{'合计':<8} {'':<12} {'':<12} {total_contracts:>8} {total_records:>10}")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='同步所有期货历史数据')
    parser.add_argument('--end', type=str, default='2026-05-25', help='结束日期 (YYYY-MM-DD)')

    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    sync_all_futures_history(end_date=end)

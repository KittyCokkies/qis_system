#!/usr/bin/env python3
"""
批量同步期货历史数据（高效版本）

使用批量查询和批量插入，大幅提高同步速度
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date, timedelta
from loguru import logger
from tqdm import tqdm
import pandas as pd
import numpy as np

from data.tonglian_source import TonglianSource
from data.database import DatabaseManager
from data.config.loader import AssetConfigLoader


def import_contracts_bulk(underlying: str, source: TonglianSource, db: DatabaseManager) -> int:
    """批量导入合约详情"""
    details = source.get_contract_details(underlying)

    if details.empty:
        logger.warning(f"在futu表未找到 {underlying} 的合约详情")
        return 0

    count = 0
    for _, row in details.iterrows():
        try:
            list_date = row.get('list_date')
            last_trade_date = row.get('last_trade_date')

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
                'symbol': row['symbol'],
                'underlying': underlying,
                'name': row['symbol'],
                'asset_class': 'future',
                'exchange': row.get('exchange', 'CFFEX'),
                'is_active': True,
                'contract_month': row.get('contract_month'),
                'list_date': list_date,
                'delist_date': last_trade_date,
                'multiplier': row.get('multiplier'),
                'tick_size': row.get('tick_size')
            })
            count += 1
        except Exception as e:
            logger.warning(f"导入 {row['symbol']} 失败: {e}")

    return count


def sync_future_range(underlying: str, start_date: date, end_date: date,
                      source: TonglianSource, db: DatabaseManager) -> int:
    """批量同步某个品种在日期范围内的所有数据"""
    # 从通联获取整个日期范围的数据
    df = source.raw_query(f"""
        SELECT
            TICKER_SYMBOL as symbol,
            TRADE_DATE as date,
            OPEN_PRICE as open,
            HIGHEST_PRICE as high,
            LOWEST_PRICE as low,
            CLOSE_PRICE as close,
            SETTL_PRICE as settle,
            TURNOVER_VOL as volume,
            TURNOVER_VALUE as amount,
            OPEN_INT as open_interest,
            LAST_TRADE_DATE as expiry_date
        FROM mkt_futd
        WHERE CONTRACT_OBJECT = '{underlying}'
        AND TRADE_DATE BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY TRADE_DATE, TICKER_SYMBOL
    """)

    if df.empty:
        logger.warning(f"{underlying} 在 {start_date} 至 {end_date} 无数据")
        return 0

    # 数据转换
    df['underlying'] = underlying
    df['date'] = pd.to_datetime(df['date']).dt.date

    # 批量插入（使用SQLAlchemy的to_sql）
    try:
        # 删除该范围内的现有数据（避免重复）
        db.execute("""
            DELETE FROM prices_future
            WHERE underlying = :underlying
            AND date BETWEEN :start_date AND :end_date
        """, {
            'underlying': underlying,
            'start_date': start_date,
            'end_date': end_date
        })

        # 批量插入
        df[['symbol', 'underlying', 'date', 'open', 'high', 'low',
            'close', 'settle', 'volume', 'amount', 'open_interest']].to_sql(
            'prices_future',
            db.engine,
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000
        )

        logger.info(f"{underlying}: 批量导入 {len(df)} 条记录")
        return len(df)
    except Exception as e:
        logger.error(f"批量导入 {underlying} 失败: {e}")
        return 0


def sync_all_futures_bulk(end_date: date = None):
    """批量同步所有期货历史数据"""
    if end_date is None:
        end_date = date(2026, 5, 25)

    logger.info("=" * 80)
    logger.info("期货历史数据批量同步（高效模式）")
    logger.info(f"结束日期: {end_date}")
    logger.info("=" * 80)

    # 加载配置
    config_loader = AssetConfigLoader()
    config_loader.load()

    futures = config_loader.futures
    logger.info(f"配置文件中共有 {len(futures)} 个期货品种")

    source = TonglianSource()
    db = DatabaseManager()

    stats = []

    for underlying, future_config in futures.items():
        # 获取该品种的起始日期
        start_date = future_config.configs[0].start_date if future_config.configs else date(2010, 1, 1)
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        # 确保不早于有数据的日期
        earliest_data_date = max(start_date, date(2000, 1, 1))

        logger.info(f"\n{'='*60}")
        logger.info(f"处理品种: {underlying} ({future_config.name})")
        logger.info(f"数据范围: {earliest_data_date} 至 {end_date}")
        logger.info(f"{'='*60}")

        # 步骤1: 导入合约信息
        logger.info("步骤1: 导入合约信息...")
        contract_count = import_contracts_bulk(underlying, source, db)

        # 步骤2: 批量同步价格数据
        logger.info("步骤2: 批量同步价格数据...")
        record_count = sync_future_range(underlying, earliest_data_date, end_date, source, db)

        stats.append({
            'underlying': underlying,
            'name': future_config.name,
            'start_date': earliest_data_date,
            'contract_count': contract_count,
            'record_count': record_count
        })

    # 打印汇总
    logger.info("\n" + "=" * 80)
    logger.info("同步完成汇总")
    logger.info("=" * 80)

    total_contracts = sum(s['contract_count'] for s in stats)
    total_records = sum(s['record_count'] for s in stats)

    logger.info(f"{'品种':<8} {'名称':<12} {'起始日期':<12} {'合约数':>8} {'记录数':>12}")
    logger.info("-" * 80)
    for s in stats:
        logger.info(f"{s['underlying']:<8} {s['name']:<12} {str(s['start_date']):<12} "
                   f"{s['contract_count']:>8} {s['record_count']:>12}")
    logger.info("-" * 80)
    logger.info(f"{'合计':<8} {'':<12} {'':<12} {total_contracts:>8} {total_records:>12}")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='批量同步期货历史数据（高效模式）')
    parser.add_argument('--end', type=str, default='2026-05-25', help='结束日期 (YYYY-MM-DD)')

    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    sync_all_futures_bulk(end_date=end)

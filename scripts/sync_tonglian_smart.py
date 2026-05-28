#!/usr/bin/env python3
"""
智能通联期货数据同步脚本

功能：
1. 首次执行：从各品种起始日期同步全量历史数据
2. 后续执行：自动增量同步到最新交易日
3. 支持定时执行（建议每日盘后 17:30 运行）

用法：
    python scripts/sync_tonglian_smart.py
    python scripts/sync_tonglian_smart.py --full-refresh  # 强制全量刷新
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple
from loguru import logger
from tqdm import tqdm
import pandas as pd

from data.tonglian_source import TonglianSource
from data.sync.tonglian_sync import TonglianSync
from data.database import DatabaseManager
from data.config.loader import AssetConfigLoader
from sqlalchemy import text

logger.remove()

# 生成带日期的日志文件名
from datetime import datetime
log_date = datetime.now().strftime('%Y-%m-%d')
log_file = f'logs/sync_tonglian_{log_date}.log'

# 控制台输出
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# 文件输出（按日期区分，方便追踪每次同步）
logger.add(log_file, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


class SmartTonglianSync:
    """智能通联数据同步器"""

    # 各品种在通联数据库中的最早数据日期
    UNDERLYING_START_DATES = {
        'IF': '2010-04-16',   # 沪深300股指期货上市日
        'IC': '2015-04-16',   # 中证500股指期货上市日
        'IM': '2022-07-22',   # 中证1000股指期货上市日
        'IH': '2015-04-16',   # 上证50股指期货上市日
        'T': '2015-03-20',    # 10年期国债期货
        'TF': '2014-09-12',   # 5年期国债期货
        'TS': '2018-08-17',   # 2年期国债期货
        'TL': '2023-04-21',   # 30年期国债期货
        'AU': '2008-01-09',   # 黄金期货
        'AG': '2012-05-10',   # 白银期货
        'CU': '1995-01-01',   # 铜期货
        'AL': '1995-01-01',   # 铝期货
        'ZN': '2007-03-26',   # 锌期货
        'PB': '2011-03-24',   # 铅期货
        'NI': '2015-03-27',   # 镍期货
        'SN': '2015-03-27',   # 锡期货
        'RB': '2009-03-27',   # 螺纹钢期货
        'HC': '2014-03-21',   # 热卷期货
        'I': '2013-10-18',    # 铁矿石期货
        'J': '2011-04-15',    # 焦炭期货
        'JM': '2013-03-22',   # 焦煤期货
        'C': '2004-09-22',    # 玉米期货
        'M': '2000-07-17',    # 豆粕期货
        'Y': '2006-01-09',    # 豆油期货
        'P': '2007-10-29',    # 棕榈油期货
        'A': '1995-01-01',    # 豆一期货
        'B': '1995-01-01',    # 豆二期货
        'CS': '2014-12-19',   # 淀粉期货
        'EG': '2018-12-10',   # 乙二醇期货
        'EB': '2019-09-26',   # 苯乙烯期货
        'PG': '2020-03-30',   # LPG期货
        'PP': '2014-02-28',   # 聚丙烯期货
        'L': '2007-07-31',    # 聚乙烯期货
        'V': '2009-05-25',    # PVC期货
        'MA': '2011-10-28',   # 甲醇期货
        'TA': '2006-12-18',   # PTA期货
        'RU': '1995-01-01',   # 天然橡胶期货
        'SC': '2018-03-26',   # 原油期货
        'FU': '2004-08-25',   # 燃料油期货
        'BU': '2013-10-09',   # 沥青期货
        'CF': '2004-06-01',   # 棉花期货
        'SR': '2006-01-06',   # 白糖期货
        'OI': '2007-06-08',   # 菜籽油期货
        'RM': '2012-12-28',   # 菜粕期货
        'SF': '2014-08-08',   # 硅铁期货
        'SM': '2014-08-08',   # 锰硅期货
        'CY': '2017-08-18',   # 棉纱期货
        'AP': '2017-12-22',   # 苹果期货
        'CJ': '2019-04-30',   # 红枣期货
        'UR': '2019-08-09',   # 尿素期货
        'SA': '2019-12-06',   # 纯碱期货
        'PF': '2020-10-12',   # 短纤期货
        'PK': '2021-02-01',   # 花生期货
    }

    def __init__(self):
        self.source = TonglianSource()
        self.sync = TonglianSync()
        self.db = DatabaseManager()
        self._ensure_contracts_table()

    def _ensure_contracts_table(self):
        """确保合约表存在"""
        try:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS assets (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) UNIQUE NOT NULL,
                    underlying VARCHAR(10) NOT NULL,
                    name VARCHAR(50),
                    asset_class VARCHAR(20) DEFAULT 'future',
                    exchange VARCHAR(10),
                    is_active BOOLEAN DEFAULT true,
                    contract_month VARCHAR(10),
                    list_date DATE,
                    delist_date DATE,
                    multiplier DECIMAL(15,4),
                    tick_size DECIMAL(10,4),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        except Exception as e:
            logger.warning(f"创建 assets 表失败（可能已存在）: {e}")

    def _get_last_sync_date(self, underlying: str) -> Optional[date]:
        """获取品种最后一次同步的日期"""
        try:
            result = self.db.execute('''
                SELECT MAX(date) as last_date
                FROM prices_future
                WHERE underlying = :underlying
            ''', {'underlying': underlying})
            row = result.fetchone()
            if row and row[0]:
                # 如果 row[0] 是字符串，转换为 date
                if isinstance(row[0], str):
                    return datetime.strptime(row[0], '%Y-%m-%d').date()
                return row[0]
        except Exception as e:
            logger.warning(f"查询 {underlying} 最后同步日期失败: {e}")
        return None

    def _get_underlyings_to_sync(self) -> List[str]:
        """获取需要同步的品种列表"""
        loader = AssetConfigLoader()
        loader.load()
        return list(loader.futures.keys())

    def _get_sync_date_range(self, underlying: str) -> Tuple[date, date]:
        """确定品种需要同步的日期范围"""
        # 获取该品种的起始日期
        start_date_str = self.UNDERLYING_START_DATES.get(underlying, '2010-01-01')
        default_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        # 查询本地最后同步日期
        last_sync = self._get_last_sync_date(underlying)

        if last_sync is None:
            # 首次同步：从品种起始日开始
            start_date = default_start
            logger.info(f"[{underlying}] 首次同步，从 {start_date} 开始")
        else:
            # 增量同步：从上次同步日期的下一天开始
            start_date = last_sync + timedelta(days=1)
            logger.info(f"[{underlying}] 增量同步，从 {start_date} 开始 (上次: {last_sync})")

        # 结束日期：今天（如果今天数据已存在，sync_daily_data 会处理重复）
        end_date = date.today()

        return start_date, end_date

    def import_contracts(self, underlying: str) -> int:
        """导入合约信息到 assets 表"""
        try:
            # 从 mkt_futd 获取合约列表
            contracts = self.source.get_future_contracts(underlying)

            # 从 futu 表获取合约详细信息
            details = self.source.get_contract_details(underlying)
            details_dict = details.set_index('symbol').to_dict('index') if not details.empty else {}

            count = 0
            for _, row in contracts.iterrows():
                symbol = row['symbol']
                detail = details_dict.get(symbol, {})

                try:
                    list_date = detail.get('list_date')
                    last_trade_date = detail.get('last_trade_date')

                    # 将 Timestamp 转换为 date 对象
                    if pd.notna(list_date) and hasattr(list_date, 'date'):
                        list_date = list_date.date()
                    if pd.notna(last_trade_date) and hasattr(last_trade_date, 'date'):
                        last_trade_date = last_trade_date.date()

                    self.db.execute('''
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
                        'underlying': row['underlying'],
                        'name': symbol,
                        'asset_class': 'future',
                        'exchange': detail.get('exchange', row.get('exchange', 'CFFEX')),
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

            logger.info(f"[{underlying}] 导入 {count} 个合约")
            return count

        except Exception as e:
            logger.error(f"[{underlying}] 合约导入失败: {e}")
            return 0

    def sync_underlying(self, underlying: str, full_refresh: bool = False) -> int:
        """同步单个品种的数据

        优化：日期范围超过30天时使用批量查询
        """
        # 步骤1: 导入合约信息
        self.import_contracts(underlying)

        # 步骤2: 确定同步日期范围
        if full_refresh:
            start_date_str = self.UNDERLYING_START_DATES.get(underlying, '2010-01-01')
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logger.info(f"[{underlying}] 强制全量刷新，从 {start_date} 开始")
        else:
            start_date, _ = self._get_sync_date_range(underlying)

        end_date = date.today()

        if start_date > end_date:
            logger.info(f"[{underlying}] 数据已是最新，无需同步")
            return 0

        days_to_sync = (end_date - start_date).days + 1
        logger.info(f"[{underlying}] 需要同步 {days_to_sync} 天")

        # 步骤3: 选择同步策略（超过7天使用批量查询）
        if days_to_sync > 7:
            logger.info(f"[{underlying}] 日期范围较大，使用批量查询模式")
            return self.sync_underlying_batch(underlying, start_date, end_date)
        else:
            # 增量模式：逐日同步
            total_records = 0
            current = start_date
            while current <= end_date:
                try:
                    records = self.sync.sync_daily_data(underlying, current, full_refresh=full_refresh)
                    total_records += records
                except Exception as e:
                    logger.error(f"同步 {underlying} {current} 失败: {e}")
                current += timedelta(days=1)
            logger.info(f"[{underlying}] 同步完成: {total_records} 条记录")
            return total_records


    def sync_underlying_batch(self, underlying: str, start_date: date, end_date: date) -> int:
        """批量同步品种数据（一次性查询日期范围）

        Args:
            underlying: 品种代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            同步记录数
        """
        from datetime import datetime

        logger.info(f"[{underlying}] 批量同步，从 {start_date} 至 {end_date}")

        # 一次性查询整个日期范围的数据
        df = self.source.get_contracts_by_date_range(
            underlying,
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.min.time())
        )

        if df.empty:
            logger.warning(f"[{underlying}] 无数据")
            return 0

        # 按日期分组处理
        total_records = 0
        grouped = df.groupby(df['date'].dt.date)

        for trade_date, day_df in grouped:
            records = day_df.to_dict('records')
            for record in records:
                self.db.execute("""
                    INSERT INTO prices_future
                    (symbol, underlying, date, open, high, low, close, settle,
                     volume, amount, open_interest)
                    VALUES (:symbol, :underlying, :date, :open, :high, :low, :close, :settle,
                     :volume, :amount, :open_interest)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        settle = EXCLUDED.settle,
                        volume = EXCLUDED.volume,
                        amount = EXCLUDED.amount,
                        open_interest = EXCLUDED.open_interest,
                        update_time = CURRENT_TIMESTAMP
                """, {
                    "symbol": record['symbol'],
                    "underlying": underlying,
                    "date": trade_date,
                    "open": record['open'],
                    "high": record['high'],
                    "low": record['low'],
                    "close": record['close'],
                    "settle": record['settle'],
                    "volume": record['volume'],
                    "amount": record['amount'],
                    "open_interest": record['open_interest']
                })
            total_records += len(records)

        logger.info(f"[{underlying}] 批量同步完成: {total_records} 条记录")
        return total_records

    def run(self, full_refresh: bool = False, underlyings: Optional[List[str]] = None):
        """
        执行同步

        Args:
            full_refresh: 是否强制全量刷新
            underlyings: 指定品种列表，None表示全部
        """
        logger.info("=" * 80)
        logger.info("智能通联期货数据同步")
        if full_refresh:
            logger.info("模式: 全量刷新")
        else:
            logger.info("模式: 智能增量")
        logger.info("=" * 80)

        # 获取品种列表
        if underlyings is None:
            underlyings = self._get_underlyings_to_sync()

        logger.info(f"共 {len(underlyings)} 个品种需要同步: {', '.join(underlyings)}")

        # 统计
        total_contracts = 0
        total_records = 0
        success_count = 0
        failed_count = 0

        for underlying in tqdm(underlyings, desc="总体进度"):
            logger.info(f"\n{'='*60}")
            logger.info(f"开始同步: {underlying}")
            logger.info('='*60)

            try:
                contracts = self.import_contracts(underlying)
                records = self.sync_underlying(underlying, full_refresh=full_refresh)

                total_contracts += contracts
                total_records += records
                success_count += 1

            except Exception as e:
                logger.error(f"[{underlying}] 同步失败: {e}")
                failed_count += 1

        # 汇总
        logger.info("\n" + "=" * 80)
        logger.info("同步完成")
        logger.info(f"成功品种: {success_count}/{len(underlyings)}")
        logger.info(f"失败品种: {failed_count}/{len(underlyings)}")
        logger.info(f"导入合约: {total_contracts} 个")
        logger.info(f"同步记录: {total_records} 条")
        logger.info("=" * 80)

        if failed_count > 0:
            logger.warning(f"有 {failed_count} 个品种同步失败")
            return False
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description='智能通联期货数据同步')
    parser.add_argument('--full-refresh', action='store_true',
                        help='强制全量刷新所有历史数据')
    parser.add_argument('--underlyings', type=str,
                        help='指定品种列表，逗号分隔 (如: IF,IC,IM)，默认全部')

    args = parser.parse_args()

    # 解析品种列表
    underlyings = None
    if args.underlyings:
        underlyings = [u.strip() for u in args.underlyings.split(',')]

    # 执行同步
    sync = SmartTonglianSync()
    success = sync.run(full_refresh=args.full_refresh, underlyings=underlyings)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

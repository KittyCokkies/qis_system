#!/usr/bin/env python3
"""
万得数据同步脚本

功能：
- 从万得(Wind)同步配置数据到本地数据库
- 支持外汇汇率、宏观指标、指数、ETF、场外基金数据
- 增量同步，自动识别新增数据
- 建议每日盘后 16:30 运行

用法：
    python scripts/sync_wind_data.py
    python scripts/sync_wind_data.py --full-refresh  # 强制全量刷新

配置来源：
    F:\airflow_qis\local\config_wind_etl.xlsx
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from loguru import logger
import pandas as pd
import argparse

from data.database import DatabaseManager
from sqlalchemy import text
from WindPy import w

# 日志配置
logger.remove()
log_date = datetime.now().strftime('%Y-%m-%d')
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
logger.add(f'logs/sync_wind_{log_date}.log', level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# 配置文件路径
CONFIG_FILE = Path('F:/airflow_qis/local/config_wind_etl.xlsx')


def get_swifquant_asset_id(row) -> str:
    """获取swifquant_asset_id，如果不存在或为空则使用tickers"""
    swifquant_id = row.get('swifquant_asset_id', '')
    if pd.notna(swifquant_id) and str(swifquant_id).strip() and str(swifquant_id).lower() != 'nan':
        return str(swifquant_id).strip()
    return row['tickers']


class WindDataSync:
    """万得数据同步器"""

    # 外汇代码映射 (万得代码 -> 实际货币代码)
    FX_CURRENCY_MAP = {
        'M0000185': 'CNY',  # 人民币汇率指数相关
        'M0000186': 'EUR',
        'M0000187': 'JPY',
        'M0000188': 'HKD',
    }

    def __init__(self, process_date=None):
        self.db = DatabaseManager()
        self.config = self._load_config()

        # 设置处理日期（默认昨天，周末顺延）
        if process_date is None:
            today = datetime.today()
            if today.weekday() == 0:  # 周一
                self.process_date = today - timedelta(days=3)
            elif today.weekday() == 6:  # 周日
                self.process_date = today - timedelta(days=2)
            else:
                self.process_date = today - timedelta(days=1)
        else:
            self.process_date = process_date

        self._init_wind_api()

    def _load_config(self) -> pd.DataFrame:
        """加载配置文件"""
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")
        df = pd.read_excel(CONFIG_FILE)
        logger.info(f"加载配置: {len(df)} 条数据")
        return df

    def _init_wind_api(self):
        """初始化万得API"""
        try:
            result = w.start()
            if result.ErrorCode != 0:
                logger.error(f"Wind API启动失败: {result.Data}")
                raise RuntimeError("Wind API启动失败")
            logger.info("Wind API连接成功")
        except Exception as e:
            logger.error(f"Wind API初始化失败: {e}")
            raise

    def run(self, full_refresh: bool = False, test_tickers: List[str] = None):
        """执行同步"""
        logger.info("="*80)
        logger.info("万得数据同步开始")
        logger.info(f"处理日期: {self.process_date.date()}")
        logger.info(f"模式: {'全量刷新' if full_refresh else '增量同步'}")
        logger.info("="*80)

        config = self.config.copy()

        # 测试模式：只处理指定的tickers
        if test_tickers:
            config = config[config['tickers'].isin(test_tickers)]
            logger.info(f"测试模式：只处理 {len(config)} 个指定asset: {test_tickers}")

        total_stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for _, row in config.iterrows():
            ticker = row['tickers']
            try:
                # 1. 提取数据
                raw_data = self.extract(row)
                if raw_data is None or raw_data.empty:
                    logger.warning(f"[{ticker}] 无数据返回，跳过")
                    total_stats['skipped'] += 1
                    continue

                # 2. 数据转换
                transformed_data = self.transform(row, raw_data)

                # 3. 数据质量检查（检查一致性，筛选增量数据）
                is_qualified, load_data = self.quality_check(row, transformed_data, full_refresh)

                if not is_qualified:
                    logger.error(f"[{ticker}] 数据质量检查失败，跳过")
                    total_stats['failed'] += 1
                    continue

                if load_data.empty:
                    logger.info(f"[{ticker}] 没有新数据需要更新")
                    total_stats['skipped'] += 1
                    continue

                # 4. 加载数据
                self.load(row, load_data)
                total_stats['success'] += 1

            except Exception as e:
                logger.error(f"[{ticker}] 同步失败: {e}")
                total_stats['failed'] += 1

        # 汇总
        logger.info("\n" + "="*80)
        logger.info("万得数据同步完成")
        logger.info(f"  成功: {total_stats['success']} 个")
        logger.info(f"  失败: {total_stats['failed']} 个")
        logger.info(f"  跳过: {total_stats['skipped']} 个")
        logger.info("="*80)

        return total_stats

    def extract(self, row) -> Optional[pd.DataFrame]:
        """从万得提取数据"""
        ticker = row['tickers']
        start_date = row['start_date']
        fields = row.get('fields', '')
        options = row['options'] if pd.notna(row['options']) and isinstance(row['options'], str) else ""
        w_function = row['function']

        logger.info(f"[{ticker}] 提取数据: {w_function}")

        if w_function == 'edb':
            # EDB经济数据库接口
            result = w.edb(ticker, start_date, self.process_date, usedf=True)
            if result[0] == 0:
                data = result[1]
                data.columns = [ticker]
                return data
            else:
                logger.error(f"[{ticker}] EDB查询失败: {result[0]}")
                return None

        elif w_function == 'wsd':
            # WSD序列数据接口
            result = w.wsd(ticker, fields, start_date, self.process_date, options, usedf=True)
            if result[0] == 0:
                data = result[1]
                data.columns = [ticker]
                return data
            else:
                logger.error(f"[{ticker}] WSD查询失败: {result[0]}")
                return None
        else:
            logger.warning(f"[{ticker}] 尚未支持的万得函数类别: {w_function}")
            return None

    def transform(self, row, raw_data: pd.DataFrame) -> pd.DataFrame:
        """数据转换和格式化"""
        ticker = row['tickers']

        transformed_data = raw_data.copy()

        # 去除空值
        transformed_data.dropna(inplace=True)

        # 按照数据库格式处理
        transformed_data = transformed_data.stack().reset_index()
        transformed_data.columns = ['trade_date', 'asset_id', 'quote']

        # 使用 swifquant_asset_id 替换 tickers
        swifquant_id = get_swifquant_asset_id(row)
        transformed_data['asset_id'] = swifquant_id

        # 日期格式
        transformed_data['trade_date'] = pd.DatetimeIndex(transformed_data['trade_date']).date

        logger.info(f"[{ticker}] 数据处理完成: {len(transformed_data)} 条")
        return transformed_data

    def quality_check(self, row, transformed_data: pd.DataFrame, full_refresh: bool) -> (bool, pd.DataFrame):
        """
        数据质量检查
        1. 检查与数据库已有数据是否一致
        2. 一致则筛选出增量数据
        3. 不一致则返回False（报错）
        """
        ticker = row['tickers']
        swifquant_id = get_swifquant_asset_id(row)
        table_name = row['table_name']

        logger.info(f"[{ticker}] 数据质量检查")

        # 全量刷新模式：跳过一致性检查，直接返回全部数据
        if full_refresh:
            logger.info(f"[{ticker}] 全量刷新模式，跳过一致性检查")
            return True, transformed_data.copy()

        # 获取目标表信息
        target_table, asset_col = self._get_target_table_info(table_name, row.get('分类', ''))
        date_col = 'date'
        quote_col = 'close' if target_table in ['prices_stock', 'prices_index'] else ('spot_rate' if target_table == 'fx_rates' else 'value')

        # 构建查询SQL
        sql_str = f"SELECT {date_col} as trade_date, {asset_col} as asset_id, {quote_col} as quote FROM {target_table} WHERE {asset_col} = :asset_id"

        # 对于外汇表，需要额外条件
        if target_table == 'fx_rates':
            sql_str += " AND to_currency = 'USD'"

        try:
            with self.db.engine.connect() as conn:
                existing_data = pd.read_sql(text(sql_str), conn, params={'asset_id': swifquant_id})
        except Exception as e:
            logger.warning(f"[{ticker}] 查询数据库失败: {e}，假设为新数据")
            existing_data = pd.DataFrame(columns=['trade_date', 'asset_id', 'quote'])

        # 如果数据库中没有该ticker的历史数据，全部作为新数据
        if existing_data.empty:
            logger.info(f"[{ticker}] 数据库中无历史数据，全部作为新数据")
            return True, transformed_data.copy()

        # 确保日期格式一致
        existing_data['trade_date'] = pd.to_datetime(existing_data['trade_date']).dt.date

        # 检查历史数据一致性（重叠日期部分）
        overlap_dates = set(transformed_data['trade_date']) & set(existing_data['trade_date'])

        if overlap_dates:
            logger.info(f"[{ticker}] 重叠日期 {len(overlap_dates)} 天，开始一致性检查")

            # 提取重叠部分数据进行比对
            new_overlap = transformed_data[transformed_data['trade_date'].isin(overlap_dates)].copy()
            db_overlap = existing_data[existing_data['trade_date'].isin(overlap_dates)].copy()

            # 合并比对
            merged = new_overlap.merge(
                db_overlap,
                on=['trade_date', 'asset_id'],
                suffixes=('_new', '_db')
            )

            # 检查数值差异（允许微小的浮点误差）
            if not merged.empty:
                merged['diff'] = abs(merged['quote_new'] - merged['quote_db'])
                max_diff = merged['diff'].max()

                if max_diff > 0.0001:  # 允许0.01%的误差
                    logger.error(f"[{ticker}] 历史数据不一致！最大差异: {max_diff}")
                    # 输出不一致的数据示例
                    inconsistent = merged[merged['diff'] > 0.0001]
                    logger.error(f"不一致数据样例:\n{inconsistent.head()}")
                    return False, pd.DataFrame()

            logger.info(f"[{ticker}] 历史数据一致性检查通过")
        else:
            logger.info(f"[{ticker}] 无重叠日期，跳过一致性检查")

        # 筛选增量数据（数据库中不存在的日期）
        existing_dates = set(existing_data['trade_date'])
        load_data = transformed_data[~transformed_data['trade_date'].isin(existing_dates)].copy()
        load_data = load_data.reset_index(drop=True)

        logger.info(f"[{ticker}] 增量数据 {len(load_data)} 条，质量检查通过")
        return True, load_data

    def _get_target_table_info(self, config_table_name: str, asset_type: str = '') -> (str, str):
        """
        将配置表名映射到实际数据库表名
        返回: (实际表名, asset_id对应的数据库字段名)
        """
        table_mapping = {
            'qis_fx_quote_info': ('fx_rates', 'from_currency'),
            'qis_market_data': ('macro_indicators', 'indicator_code'),
        }

        if config_table_name in table_mapping:
            return table_mapping[config_table_name]
        elif config_table_name == 'qis_underlying_quote_info':
            # 根据资产类型选择表
            if 'index' in asset_type:
                return ('prices_index', 'symbol')
            else:
                return ('prices_stock', 'symbol')
        else:
            return (config_table_name, 'asset_id')

    def _ensure_asset_exists(self, ticker: str, asset_name: str, asset_class: str, exchange: str):
        """确保资产存在于assets表中"""
        try:
            with self.db.engine.connect() as conn:
                # 检查资产是否存在
                result = conn.execute(
                    text("SELECT symbol FROM assets WHERE symbol = :symbol"),
                    {'symbol': ticker}
                )
                if result.fetchone() is None:
                    # 插入新资产
                    conn.execute(
                        text("""
                            INSERT INTO assets (symbol, underlying, name, asset_class, exchange, is_active)
                            VALUES (:symbol, :underlying, :name, :asset_class, :exchange, TRUE)
                            ON CONFLICT (symbol) DO NOTHING
                        """),
                        {
                            'symbol': ticker,
                            'underlying': ticker.split('.')[0] if '.' in ticker else ticker,
                            'name': asset_name if asset_name else ticker,
                            'asset_class': asset_class,
                            'exchange': exchange
                        }
                    )
                    logger.info(f"[{ticker}] 已添加到assets表")
        except Exception as e:
            logger.warning(f"[{ticker}] 检查/添加资产信息失败: {e}")

    def load(self, row, load_data: pd.DataFrame):
        """将数据加载到数据库"""
        ticker = row['tickers']
        config_table_name = row['table_name']
        asset_type = row.get('分类', '')
        asset_name = row.get('swifquant_asset_id', ticker)

        # 获取表映射信息
        target_table, asset_col = self._get_target_table_info(config_table_name, asset_type)

        logger.info(f"[{ticker}] 加载数据到 {target_table} (配置表: {config_table_name})")

        # 对于prices_stock和prices_index，需要先确保资产存在
        if target_table in ['prices_stock', 'prices_index']:
            # 确定资产类别和交易所
            if 'etf' in asset_type:
                asset_class = 'etf'
            elif 'index' in asset_type:
                asset_class = 'index'
            else:
                asset_class = 'stock'

            # 确定交易所
            if '.SH' in ticker:
                exchange = 'SSE'
            elif '.SZ' in ticker:
                exchange = 'SZSE'
            else:
                exchange = 'UNKNOWN'

            self._ensure_asset_exists(ticker, asset_name, asset_class, exchange)

        try:
            with self.db.engine.connect() as conn:
                with conn.begin():
                    for _, data_row in load_data.iterrows():
                        trade_date = data_row['trade_date']
                        asset_id = data_row['asset_id']
                        quote = float(data_row['quote'])

                        if target_table == 'fx_rates':
                            # 外汇表 - 需要将asset_id解析为货币对
                            if ticker in self.FX_CURRENCY_MAP:
                                from_curr = self.FX_CURRENCY_MAP[ticker]
                            else:
                                from_curr = asset_id if len(asset_id) <= 3 else 'CNY'

                            sql = """
                                INSERT INTO fx_rates (date, from_currency, to_currency, spot_rate)
                                VALUES (:date, :from_curr, 'USD', :rate)
                                ON CONFLICT (date, from_currency, to_currency) DO UPDATE SET
                                    spot_rate = EXCLUDED.spot_rate
                            """
                            values = {
                                'date': trade_date,
                                'from_curr': from_curr,
                                'rate': quote
                            }

                        elif target_table == 'macro_indicators':
                            # 宏观指标表
                            sql = """
                                INSERT INTO macro_indicators (indicator_code, indicator_name, date, period_type, value, unit)
                                VALUES (:code, :name, :date, :period, :value, :unit)
                                ON CONFLICT (indicator_code, date) DO UPDATE SET
                                    value = EXCLUDED.value
                            """
                            values = {
                                'code': asset_id,
                                'name': asset_name,
                                'date': trade_date,
                                'period': 'daily',
                                'value': quote,
                                'unit': '%'
                            }

                        elif target_table == 'prices_stock':
                            # 股票价格表 (ETF/股票)
                            sql = """
                                INSERT INTO prices_stock (symbol, date, close)
                                VALUES (:symbol, :date, :close)
                                ON CONFLICT (symbol, date) DO UPDATE SET
                                    close = EXCLUDED.close
                            """
                            values = {
                                'symbol': ticker,
                                'date': trade_date,
                                'close': quote
                            }

                        elif target_table == 'prices_index':
                            # 指数价格表
                            sql = """
                                INSERT INTO prices_index (symbol, date, close)
                                VALUES (:symbol, :date, :close)
                                ON CONFLICT (symbol, date) DO UPDATE SET
                                    close = EXCLUDED.close
                            """
                            values = {
                                'symbol': ticker,
                                'date': trade_date,
                                'close': quote
                            }

                        else:
                            # 通用插入
                            sql = f"""
                                INSERT INTO {target_table} (trade_date, asset_id, quote)
                                VALUES (:date, :asset_id, :quote)
                            """
                            values = {
                                'date': trade_date,
                                'asset_id': asset_id,
                                'quote': quote
                            }

                        conn.execute(text(sql), values)

            logger.info(f"[{ticker}] 数据加载完成: {len(load_data)} 条")

        except Exception as e:
            logger.error(f"[{ticker}] 数据加载失败: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(description='万得数据同步脚本')
    parser.add_argument('--full-refresh', action='store_true',
                       help='强制全量刷新（从头开始同步）')
    parser.add_argument('--test', action='store_true',
                       help='测试模式（只处理部分数据）')
    parser.add_argument('--ticker', type=str,
                       help='指定单个ticker进行测试')

    args = parser.parse_args()

    # 确定测试ticker
    test_tickers = None
    if args.ticker:
        test_tickers = [args.ticker]
    elif args.test:
        # 默认测试ticker：每类选一个
        test_tickers = [
            'M0000185',    # 外汇
            'M0041653',    # r007
            '000300.SH',   # 沪深300
        ]

    # 执行同步
    sync = WindDataSync()
    stats = sync.run(full_refresh=args.full_refresh, test_tickers=test_tickers)

    # 如果有失败，返回非0退出码
    if stats['failed'] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

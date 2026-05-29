#!/usr/bin/env python3
"""
彭博Excel数据同步脚本

功能：
- 每日自动读取彭博Excel文件
- 分类同步到不同表（prices_index, fx_rates, prices_future, assets）
- 增量更新，只同步新增数据

数据映射（方案A）：
- 股票指数 → prices_index
- 外汇/汇率 → fx_rates
- DMA结算价/最新价 → prices_future
- DMA通知日 → assets.delist_date（复用字段，存first_notice_date）
- 债券/商品指数 → prices_index

Usage:
    python scripts/sync_bloomberg_excel.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from loguru import logger
import pandas as pd

from data.database import DatabaseManager

# 统一日志配置
from scripts.sync_logger import setup_logger
logger = setup_logger('bloomberg')

# 彭博Excel文件路径
BLOOMBERG_FILE = r'Z:\每日更新\数据\彭博\bbg_data_new.xlsx'

# 数据分类映射
SYMBOL_CATEGORIES = {
    # 股票指数 -> prices_index
    'index': [
        'STAR50 Index', 'HSI Index', 'HSTECH Index', 'VIX Index',
        'SGIXBTU Index', 'SGIXBFV Index', 'SGIXBTY Index', 'SGIXBWN Index',
        'SGIXBRX Index', 'IND1JP10 Index', 'SGBVRES1 Index', 'SGBVRNQ1 Index',
        'SGBVRGX1 Index', 'SGBVRNK1 Index', 'SGBVRVG1 Index', 'SGICGCSR Index',
        'SGICCOSR Index', 'SGICHGSR Index', 'SGBVRHC1 Index', 'SGIXTFMM Index',
        'UBCSR9TS Index', 'XUBSR9TD Index', 'UBCSGWHV Index', 'COMCRRY Index',
        'BNPXF3PX Index', 'BNPXD6XC Index', 'BPMMMTWU Index', 'BNPXCDXS Index',
        'BNPXTDUN Index', 'BNPXTPRH Index', 'BNPXTPRU Index', 'BNPXTPRE Index',
        'BNPXTPRJ Index', 'UBCSSWMP Index', 'UBCSSW2P Index', 'XUBSTUL1 Index',
        'JPUS2525 Index', 'JPOSHVSN Index', 'JPUSNQIM Index', 'JPOSIVSS Index',
        'JPOSCUVS Index', 'JPOSVWHU Index', 'JPOSSVV1 Index', 'JCUBUXY1 Index',
        'JPCVMM02 Index', 'JMABLCCU Index', 'JMABSKNS Index', 'BCOMTR Index',
        'LEGATRUU Index', 'DYN225', 'JPUSNQTL Index', 'JPOSIGN2 Index',
        'JMAB618E Index', 'ECHINXT CH Equity'
    ],
    # 外汇 -> fx_rates
    'fx': [
        'CNH L160 Curncy', 'JPYCNH L160 Curncy', 'EURCNH L160 Curncy',
        'HKDCNH L160 Curncy', 'HKDUSD L160 Curncy', 'HKDCNH Curncy',
        'CNYUSD BFIX Curncy', 'USDCNY Curncy', 'USDCNH Curncy'
    ],
    # DMA期货 -> prices_future + assets
    'dma_futures': [
        'DMA_settle', 'DMA_last', 'DMA_ltd',
        'HCTA_settle', 'HCTA_volume', 'HCTA_ltd'
    ]
}

# Bloomberg代码到内部代码的映射
SYMBOL_MAPPING = {
    # 可以根据需要添加映射
    'STAR50 Index': 'STAR50',
    'HSI Index': 'HSI',
    'HSTECH Index': 'HSTECH',
    'VIX Index': 'VIX',
    'CNH L160 Curncy': 'CNH',
    'USDCNY Curncy': 'USDCNY',
    'USDCNH Curncy': 'USDCNH',
}


class BloombergExcelSync:
    """彭博Excel数据同步器"""

    def __init__(self):
        self.db = DatabaseManager()
        self.file_path = BLOOMBERG_FILE

    def _get_category(self, sheet_name: str) -> Optional[str]:
        """根据工作表名称判断数据类型"""
        for category, symbols in SYMBOL_CATEGORIES.items():
            if sheet_name in symbols:
                return category
        return None

    def _get_internal_symbol(self, bloomberg_code: str) -> str:
        """将Bloomberg代码转换为内部代码"""
        return SYMBOL_MAPPING.get(bloomberg_code, bloomberg_code)

    def _get_last_sync_date(self, symbol: str, table: str) -> Optional[date]:
        """获取某symbol在表中的最后同步日期"""
        try:
            if table == 'prices_index':
                result = self.db.execute('''
                    SELECT MAX(date) as last_date
                    FROM prices_index
                    WHERE symbol = :symbol
                ''', {'symbol': symbol})
            elif table == 'fx_rates':
                # 对于外汇，使用from_currency匹配
                result = self.db.execute('''
                    SELECT MAX(date) as last_date
                    FROM fx_rates
                    WHERE from_currency = :symbol
                ''', {'symbol': symbol})
            elif table == 'prices_future':
                result = self.db.execute('''
                    SELECT MAX(date) as last_date
                    FROM prices_future
                    WHERE underlying = :symbol
                ''', {'symbol': symbol})
            else:
                return None

            row = result.fetchone()
            if row and row[0]:
                if isinstance(row[0], str):
                    return datetime.strptime(row[0], '%Y-%m-%d').date()
                return row[0]
        except Exception as e:
            logger.warning(f"查询 {symbol} 最后同步日期失败: {e}")
        return None

    def sync_index_data(self, df: pd.DataFrame, symbol: str) -> int:
        """同步指数数据到 prices_index"""
        internal_symbol = self._get_internal_symbol(symbol)
        last_date = self._last_sync_date('prices_index', internal_symbol)

        count = 0
        for _, row in df.iterrows():
            trade_date = row.iloc[0]
            value = row.iloc[1]

            if pd.isna(trade_date) or pd.isna(value):
                continue

            trade_date = pd.to_datetime(trade_date).date()

            # 增量检查
            if last_date and trade_date <= last_date:
                continue

            try:
                # 先确保 asset 存在
                self.db.execute('''
                    INSERT INTO assets (symbol, underlying, name, asset_class, exchange, is_active)
                    VALUES (:symbol, :underlying, :name, :asset_class, :exchange, :is_active)
                    ON CONFLICT (symbol) DO NOTHING
                ''', {
                    'symbol': internal_symbol,
                    'underlying': internal_symbol,
                    'name': symbol,
                    'asset_class': 'index',
                    'exchange': 'BLOOMBERG',
                    'is_active': True
                })
                
                # 再插入价格数据
                self.db.execute('''
                    INSERT INTO prices_index
                    (symbol, date, close, update_time)
                    VALUES (:symbol, :date, :close, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        close = EXCLUDED.close,
                        update_time = CURRENT_TIMESTAMP
                ''', {
                    'symbol': internal_symbol,
                    'date': trade_date,
                    'close': float(value)
                })
                count += 1
            except Exception as e:
                logger.warning(f"插入 {symbol} {trade_date} 失败: {e}")

        logger.info(f"[{symbol}] 同步 {count} 条指数记录到 prices_index")
        return count

    def sync_fx_data(self, df: pd.DataFrame, symbol: str) -> int:
        """同步外汇数据到 fx_rates"""
        # 解析货币对
        if 'CNH' in symbol:
            from_curr, to_curr = 'CNH', 'USD'
        elif 'USDCNY' in symbol:
            from_curr, to_curr = 'USD', 'CNY'
        elif 'USDCNH' in symbol:
            from_curr, to_curr = 'USD', 'CNH'
        else:
            # 默认提取前3个字符
            from_curr = symbol[:3] if len(symbol) >= 3 else symbol
            to_curr = 'USD'

        last_date = self._get_last_sync_date(from_curr, 'fx_rates')

        count = 0
        for _, row in df.iterrows():
            trade_date = row.iloc[0]
            value = row.iloc[1]

            if pd.isna(trade_date) or pd.isna(value):
                continue

            trade_date = pd.to_datetime(trade_date).date()

            # 增量检查
            if last_date and trade_date <= last_date:
                continue

            try:
                self.db.execute('''
                    INSERT INTO fx_rates
                    (from_currency, to_currency, date, spot_rate, update_time)
                    VALUES (:from_curr, :to_curr, :date, :rate, CURRENT_TIMESTAMP)
                    ON CONFLICT (from_currency, to_currency, date) DO UPDATE SET
                        spot_rate = EXCLUDED.spot_rate,
                        update_time = CURRENT_TIMESTAMP
                ''', {
                    'from_curr': from_curr,
                    'to_curr': to_curr,
                    'date': trade_date,
                    'rate': float(value)
                })
                count += 1
            except Exception as e:
                logger.warning(f"插入外汇 {symbol} {trade_date} 失败: {e}")

        logger.info(f"[{symbol}] 同步 {count} 条外汇记录到 fx_rates")
        return count

    def sync_dma_prices(self, df: pd.DataFrame, sheet_name: str) -> int:
        """同步DMA价格数据到 prices_future"""
        # DMA_settle/DMA_last 结构：第一列是合约代码，其他列是日期

        count = 0
        # 获取合约代码列（第一列）
        contract_col = df.columns[0]

        # 遍历每一行（每个合约）
        for _, row in df.iterrows():
            contract_code = str(row[contract_col])

            # 遍历日期列（从第二列开始）
            for col in df.columns[1:]:
                # 列名是日期
                try:
                    if isinstance(col, str):
                        trade_date = pd.to_datetime(col).date()
                    else:
                        trade_date = col.date() if hasattr(col, 'date') else pd.to_datetime(col).date()
                except:
                    continue  # 跳过无效日期

                value = row[col]

                if pd.isna(value):
                    continue

                # 判断是结算价还是最新价
                if 'settle' in sheet_name.lower():
                    settle_val = float(value)
                    close_val = None
                elif 'last' in sheet_name.lower():
                    settle_val = None
                    close_val = float(value)
                else:
                    continue

                try:
                    self.db.execute('''
                        INSERT INTO prices_future
                        (symbol, underlying, date, settle, close, update_time)
                        VALUES (:symbol, :underlying, :date, :settle, :close, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            settle = COALESCE(EXCLUDED.settle, prices_future.settle),
                            close = COALESCE(EXCLUDED.close, prices_future.close),
                            update_time = CURRENT_TIMESTAMP
                    ''', {
                        'symbol': contract_code,
                        'underlying': 'DMA',
                        'date': trade_date,
                        'settle': settle_val,
                        'close': close_val
                    })
                    count += 1
                except Exception as e:
                    logger.warning(f"插入DMA {contract_code} {trade_date} 失败: {e}")

        logger.info(f"[{sheet_name}] 同步 {count} 条DMA价格记录到 prices_future")
        return count

    def sync_dma_notice_date(self, df: pd.DataFrame) -> int:
        """同步DMA第一通知日到 assets.delist_date"""
        # DMA_ltd表结构：合约代码 + 通知日
        # 使用delist_date字段存储first_notice_date（方案A）

        count = 0
        for _, row in df.iterrows():
            contract_code = str(row.iloc[0])
            notice_date = row.iloc[1]

            if pd.isna(contract_code) or pd.isna(notice_date):
                continue

            notice_date = pd.to_datetime(notice_date).date()

            try:
                # 检查合约是否已存在
                result = self.db.execute('''
                    SELECT symbol FROM assets WHERE symbol = :symbol
                ''', {'symbol': contract_code})

                if result.fetchone():
                    # 更新delist_date（存first_notice_date）
                    self.db.execute('''
                        UPDATE assets
                        SET delist_date = :notice_date,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE symbol = :symbol
                    ''', {
                        'symbol': contract_code,
                        'notice_date': notice_date
                    })
                else:
                    # 插入新合约
                    self.db.execute('''
                        INSERT INTO assets
                        (symbol, underlying, name, asset_class, exchange,
                         is_active, delist_date)
                        VALUES (:symbol, :underlying, :name, :asset_class, :exchange,
                                :is_active, :delist_date)
                        ON CONFLICT (symbol) DO UPDATE SET
                            delist_date = EXCLUDED.delist_date,
                            updated_at = CURRENT_TIMESTAMP
                    ''', {
                        'symbol': contract_code,
                        'underlying': 'DMA',
                        'name': contract_code,
                        'asset_class': 'future',
                        'exchange': 'CME',  # DMA通常在CME交易
                        'is_active': True,
                        'delist_date': notice_date  # 方案A：存first_notice_date
                    })
                count += 1
            except Exception as e:
                logger.warning(f"更新DMA通知日 {contract_code} 失败: {e}")

        logger.info(f"[DMA_ltd] 同步 {count} 条DMA通知日到 assets")
        return count

    def _last_sync_date(self, table: str, symbol: str) -> Optional[date]:
        """获取最后同步日期"""
        return self._get_last_sync_date(symbol, table)

    def run(self):
        """执行同步"""
        logger.info("="*80)
        logger.info("彭博Excel数据同步开始")
        logger.info(f"文件: {self.file_path}")
        logger.info("="*80)

        # 检查文件是否存在
        if not Path(self.file_path).exists():
            logger.error(f"文件不存在: {self.file_path}")
            return False

        # 读取Excel
        try:
            xl = pd.ExcelFile(self.file_path)
            logger.info(f"共 {len(xl.sheet_names)} 个工作表")
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return False

        # 统计
        total_stats = {
            'index': 0,
            'fx': 0,
            'dma_prices': 0,
            'dma_notice': 0,
            'skipped': 0
        }

        # 遍历所有工作表
        for sheet_name in xl.sheet_names:
            category = self._get_category(sheet_name)

            if not category:
                logger.debug(f"跳过未分类工作表: {sheet_name}")
                total_stats['skipped'] += 1
                continue

            try:
                df = pd.read_excel(self.file_path, sheet_name=sheet_name)

                if df.empty:
                    logger.warning(f"[{sheet_name}] 工作表为空")
                    continue

                logger.info(f"\n处理 [{sheet_name}] -> {category}")

                if category == 'index':
                    count = self.sync_index_data(df, sheet_name)
                    total_stats['index'] += count

                elif category == 'fx':
                    count = self.sync_fx_data(df, sheet_name)
                    total_stats['fx'] += count

                elif category == 'dma_futures':
                    if 'ltd' in sheet_name.lower():
                        # DMA通知日 -> assets
                        count = self.sync_dma_notice_date(df)
                        total_stats['dma_notice'] += count
                    else:
                        # DMA价格 -> prices_future
                        count = self.sync_dma_prices(df, sheet_name)
                        total_stats['dma_prices'] += count

            except Exception as e:
                logger.error(f"处理 [{sheet_name}] 失败: {e}")

        # 汇总
        logger.info("\n" + "="*80)
        logger.info("同步完成")
        logger.info(f"  指数数据: {total_stats['index']} 条")
        logger.info(f"  外汇数据: {total_stats['fx']} 条")
        logger.info(f"  DMA价格: {total_stats['dma_prices']} 条")
        logger.info(f"  DMA通知日: {total_stats['dma_notice']} 条")
        logger.info(f"  跳过: {total_stats['skipped']} 个工作表")
        logger.info("="*80)

        return True


def main():
    sync = BloombergExcelSync()
    success = sync.run()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

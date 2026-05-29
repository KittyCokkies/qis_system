#!/usr/bin/env python3
"""
修复缺失的assets记录
检查prices_stock和prices_index中的symbol，确保都在assets表中有记录
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import DatabaseManager
from sqlalchemy import text
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def get_exchange(symbol: str) -> str:
    """根据symbol确定交易所"""
    if '.SH' in symbol:
        return 'SSE'
    elif '.SZ' in symbol:
        return 'SZSE'
    elif '.OF' in symbol:
        return 'OF'
    elif '.L' in symbol:
        return 'LSE'
    elif '.BAT' in symbol:
        return 'BAT'
    elif symbol.endswith('.GI') or symbol.endswith('.HI') or symbol.endswith('.CSI') or symbol.endswith('.WI'):
        return 'INDEX'
    else:
        return 'UNKNOWN'


def get_asset_class(symbol: str) -> str:
    """根据symbol确定资产类别"""
    # ETF列表
    etf_symbols = [
        '0JGN.L', '588000.SH', 'INDA.BAT', '159732.SZ', '159755.SZ',
        '159852.SZ', '159985.SZ', '159992.SZ', '159995.SZ', '511380.SH',
        '512400.SH', '512660.SH', '512890.SH', '515790.SH', '515980.SH',
        '562500.SH', '159915.SZ'
    ]

    # 场外基金
    fund_symbols = ['007994.OF', '110026.OF', '501018.SH']

    # 指数
    index_suffixes = ['.SH', '.SZ', '.CSI', '.WI', '.GI', '.HI', '.CCI', '.CS']

    if symbol in etf_symbols:
        return 'etf'
    elif symbol in fund_symbols:
        return 'fund'
    elif any(symbol.endswith(suffix) for suffix in index_suffixes):
        return 'index'
    else:
        return 'stock'


def fix_missing_assets():
    """修复缺失的assets记录"""
    db = DatabaseManager()

    logger.info("="*80)
    logger.info("开始检查并修复缺失的assets记录")
    logger.info("="*80)

    # 检查 prices_stock 中的symbol
    with db.engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT ps.symbol
            FROM prices_stock ps
            LEFT JOIN assets a ON ps.symbol = a.symbol
            WHERE a.symbol IS NULL
        """))
        missing_stock = [row[0] for row in result.fetchall()]

    # 检查 prices_index 中的symbol
    with db.engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT pi.symbol
            FROM prices_index pi
            LEFT JOIN assets a ON pi.symbol = a.symbol
            WHERE a.symbol IS NULL
        """))
        missing_index = [row[0] for row in result.fetchall()]

    missing_symbols = set(missing_stock + missing_index)

    if not missing_symbols:
        logger.info("所有symbol都已存在于assets表中")
        return

    logger.info(f"发现 {len(missing_symbols)} 个缺失的assets记录")

    # 插入缺失的assets
    added_count = 0
    for symbol in missing_symbols:
        asset_class = get_asset_class(symbol)
        exchange = get_exchange(symbol)

        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    conn.execute(
                        text("""
                            INSERT INTO assets (symbol, underlying, name, asset_class, exchange, is_active)
                            VALUES (:symbol, :underlying, :name, :asset_class, :exchange, TRUE)
                            ON CONFLICT (symbol) DO NOTHING
                        """),
                        {
                            'symbol': symbol,
                            'underlying': symbol.split('.')[0] if '.' in symbol else symbol,
                            'name': symbol,
                            'asset_class': asset_class,
                            'exchange': exchange
                        }
                    )
                    logger.info(f"  {symbol} -> {asset_class} ({exchange})")
                    added_count += 1
        except Exception as e:
            logger.error(f"  {symbol} 添加失败: {e}")

    logger.info("="*80)
    logger.info(f"修复完成，共添加 {added_count} 个assets记录")
    logger.info("="*80)


if __name__ == "__main__":
    fix_missing_assets()

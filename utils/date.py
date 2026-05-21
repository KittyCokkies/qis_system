from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd


def get_trade_dates(
    start_date: datetime,
    end_date: datetime,
    market: str = "SSE"
) -> List[datetime]:
    """获取交易日列表

    Args:
        start_date: 开始日期
        end_date: 结束日期
        market: 市场代码 SSE/SZSE

    Returns:
        交易日列表
    """
    # 简化实现：排除周末
    dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # 周一到周五
            dates.append(current)
        current += timedelta(days=1)
    return dates


def get_previous_trade_date(
    date: datetime,
    n: int = 1,
    market: str = "SSE"
) -> datetime:
    """获取前N个交易日

    Args:
        date: 基准日期
        n: 往前推N个交易日
        market: 市场代码

    Returns:
        前N个交易日
    """
    current = date
    count = 0
    while count < n:
        current -= timedelta(days=1)
        if current.weekday() < 5:  # 工作日
            count += 1
    return current


def get_next_trade_date(
    date: datetime,
    n: int = 1,
    market: str = "SSE"
) -> datetime:
    """获取后N个交易日"""
    current = date
    count = 0
    while count < n:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return current


def resample_to_week(df: pd.DataFrame) -> pd.DataFrame:
    """将日频数据转为周频"""
    return df.resample('W-FRI').last()


def resample_to_month(df: pd.DataFrame) -> pd.DataFrame:
    """将日频数据转为月频"""
    return df.resample('ME').last()


def timestamp_to_datetime(ts) -> datetime:
    """将各种时间格式转为datetime"""
    if isinstance(ts, datetime):
        return ts
    elif isinstance(ts, str):
        return pd.to_datetime(ts)
    elif isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime()
    else:
        raise ValueError(f"Cannot convert {type(ts)} to datetime")
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Union

import pandas as pd


class DataSourceBase(ABC):
    """数据源抽象基类

    定义数据源的标准接口。子类只需要实现其支持的方法，
    不支持的接口可以保持默认行为（返回空数据或抛出异常）。

    子类应该通过构造函数或属性标明自己支持哪些数据类型：
        supports_price = True/False  # 是否支持行情数据
        supports_fundamentals = True/False  # 是否支持财务数据
        supports_minute = True/False  # 是否支持分钟数据
    """

    # 数据源能力标识（子类应重写）
    supports_daily_price = True
    supports_minute_price = False
    supports_fundamentals = False
    supports_index_components = False
    supports_trade_calendar = False

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据

        Args:
            symbol: 标的代码或代码列表
            start_date: 开始日期
            end_date: 结束日期
            fields: 需要的字段列表，None表示全部

        Returns:
            DataFrame with columns: [symbol, date, open, high, low, close, volume, ...]
        """
        if not self.supports_daily_price:
            raise NotImplementedError(f"{self.__class__.__name__} does not support daily price data")
        return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级行情数据

        Args:
            symbol: 标的代码
            start_date: 开始日期
            end_date: 结束日期
            freq: 频率，如 "1min", "5min", "15min"

        Returns:
            DataFrame with OHLCV data
        """
        if not self.supports_minute_price:
            raise NotImplementedError(f"{self.__class__.__name__} does not support minute price data")
        return pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取基本面数据

        Args:
            symbol: 标的代码或列表
            fields: 财务字段列表
            date: 报告期日期

        Returns:
            DataFrame with fundamental data
        """
        if not self.supports_fundamentals:
            raise NotImplementedError(f"{self.__class__.__name__} does not support fundamental data")
        return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股

        Args:
            index_code: 指数代码，如 "000300.SH"
            date: 查询日期

        Returns:
            成分股代码列表
        """
        if not self.supports_index_components:
            raise NotImplementedError(f"{self.__class__.__name__} does not support index components")
        return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历

        Args:
            start_date: 开始日期
            end_date: 结束日期
            market: 市场代码，SSE/深交所

        Returns:
            DataFrame with trade dates
        """
        if not self.supports_trade_calendar:
            raise NotImplementedError(f"{self.__class__.__name__} does not support trade calendar")
        return pd.DataFrame()

    def normalize_symbol(self, symbol: str) -> str:
        """标准化标的代码

        Args:
            symbol: 原始代码，如 "000001" 或 "000001.SZ"

        Returns:
            标准化代码
        """
        symbol = symbol.strip().upper()
        if "." in symbol:
            return symbol
        # 根据代码规则判断交易所
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        elif symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        elif symbol.startswith(("5", "1")):
            return f"{symbol}.SH"
        return symbol

    def normalize_symbols(self, symbols: List[str]) -> List[str]:
        """批量标准化标的代码"""
        return [self.normalize_symbol(s) for s in symbols]

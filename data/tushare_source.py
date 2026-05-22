from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
import tushare as ts
from loguru import logger

from config import get_settings
from data.base import DataSourceBase


class TushareSource(DataSourceBase):
    """Tushare数据源

    Tushare提供专业的金融数据接口，数据质量高但需要积分
    适合需要高质量数据的场景
    """

    supports_daily_price = True
    supports_minute_price = True  # 需要高级权限
    supports_fundamentals = True
    supports_index_components = True
    supports_trade_calendar = True

    def __init__(self, token: Optional[str] = None):
        super().__init__()
        settings = get_settings()
        self.token = token or settings.datasource.tushare_token

        if self.token:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            logger.info("TushareSource initialized with token")
        else:
            self.pro = None
            logger.warning("TushareSource initialized without token")

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据"""
        if not self.pro:
            logger.error("Tushare not initialized with token")
            return pd.DataFrame()

        if isinstance(symbol, list):
            symbol = ",".join([s.replace(".SZ", "").replace(".SH", "") for s in symbol])
        else:
            symbol = symbol.replace(".SZ", "").replace(".SH", "")

        start_str = start_date.strftime("%Y%m%d") if start_date else None
        end_str = end_date.strftime("%Y%m%d") if end_date else None

        try:
            df = self.pro.daily(
                ts_code=symbol,
                start_date=start_str,
                end_date=end_str
            )

            if df.empty:
                return df

            # 标准化列名
            df.rename(columns={
                "ts_code": "symbol",
                "trade_date": "date",
                "vol": "volume"
            }, inplace=True)

            df["date"] = pd.to_datetime(df["date"])
            df["symbol"] = df["symbol"].apply(self.normalize_symbol)

            # 调整列顺序
            col_order = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
            df = df[[col for col in col_order if col in df.columns]]

            return df

        except Exception as e:
            logger.warning(f"Failed to get daily price from Tushare: {e}")
            return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级数据（需要较高权限）"""
        if not self.pro:
            return pd.DataFrame()

        symbol = symbol.replace(".SZ", "").replace(".SH", "")

        try:
            # Tushare分钟数据接口
            freq_map = {
                "1min": "1min",
                "5min": "5min",
                "15min": "15min",
                "30min": "30min",
                "60min": "60min"
            }
            ts_freq = freq_map.get(freq, "1min")

            df = ts.pro_bar(
                ts_code=symbol,
                freq=ts_freq,
                start_date=start_date.strftime("%Y-%m-%d %H:%M:%S") if start_date else None,
                end_date=end_date.strftime("%Y-%m-%d %H:%M:%S") if end_date else None
            )

            if df.empty:
                return df

            df.rename(columns={
                "ts_code": "symbol",
                "trade_date": "datetime",
                "vol": "volume"
            }, inplace=True)

            df["datetime"] = pd.to_datetime(df["datetime"])
            df["symbol"] = df["symbol"].apply(self.normalize_symbol)

            return df

        except Exception as e:
            logger.warning(f"Failed to get minute price from Tushare: {e}")
            return pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取财务数据"""
        if not self.pro:
            return pd.DataFrame()

        if isinstance(symbol, list):
            symbol = ",".join([s.replace(".SZ", "").replace(".SH", "") for s in symbol])
        else:
            symbol = symbol.replace(".SZ", "").replace(".SH", "")

        end_date = date.strftime("%Y%m%d") if date else datetime.now().strftime("%Y%m%d")

        try:
            # 获取利润表数据
            df = self.pro.income(
                ts_code=symbol,
                end_date=end_date,
                fields=",".join(fields) if fields else None
            )

            if not df.empty:
                df.rename(columns={
                    "ts_code": "symbol",
                    "end_date": "report_date"
                }, inplace=True)
                df["report_date"] = pd.to_datetime(df["report_date"])

            return df

        except Exception as e:
            logger.warning(f"Failed to get fundamentals from Tushare: {e}")
            return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股"""
        if not self.pro:
            return []

        # 转换为Tushare格式
        ts_code = index_code.replace(".SH", "").replace(".SZ", "")

        try:
            trade_date = date.strftime("%Y%m%d") if date else None

            df = self.pro.index_weight(
                index_code=ts_code,
                trade_date=trade_date
            )

            if not df.empty:
                return df["con_code"].tolist()

            return []

        except Exception as e:
            logger.warning(f"Failed to get index components from Tushare: {e}")
            return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历"""
        if not self.pro:
            return pd.DataFrame()

        exchange = market if market in ["SSE", "SZSE"] else "SSE"
        start_str = start_date.strftime("%Y%m%d") if start_date else None
        end_str = end_date.strftime("%Y%m%d") if end_date else None

        try:
            df = self.pro.trade_cal(
                exchange=exchange,
                start_date=start_str,
                end_date=end_str
            )

            if not df.empty:
                df.rename(columns={
                    "cal_date": "date",
                    "is_open": "is_trading_day"
                }, inplace=True)
                df["date"] = pd.to_datetime(df["date"])
                df["is_trading_day"] = df["is_trading_day"] == 1

            return df

        except Exception as e:
            logger.warning(f"Failed to get trade calendar from Tushare: {e}")
            return pd.DataFrame()

    def get_daily_basic(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取每日指标（市值、PE、PB等）"""
        if not self.pro:
            return pd.DataFrame()

        try:
            ts_code = symbol.replace(".SZ", "").replace(".SH", "") if symbol else None
            start_str = start_date.strftime("%Y%m%d") if start_date else None
            end_str = end_date.strftime("%Y%m%d") if end_date else None

            df = self.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str
            )

            if not df.empty:
                df.rename(columns={
                    "ts_code": "symbol",
                    "trade_date": "date"
                }, inplace=True)
                df["date"] = pd.to_datetime(df["date"])
                df["symbol"] = df["symbol"].apply(self.normalize_symbol)

            return df

        except Exception as e:
            logger.warning(f"Failed to get daily basic from Tushare: {e}")
            return pd.DataFrame()

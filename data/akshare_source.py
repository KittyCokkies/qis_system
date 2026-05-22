from datetime import datetime
from typing import List, Optional, Union

import akshare as ak
import pandas as pd
from loguru import logger

from data.base import DataSourceBase


class AKShareSource(DataSourceBase):
    """AKShare数据源

    AKShare是开源的Python金融数据接口库，数据来源于东方财富等
    适合获取A股、基金、期货等数据
    """

    supports_daily_price = True
    supports_minute_price = True
    supports_fundamentals = True
    supports_index_components = True
    supports_trade_calendar = True

    def __init__(self):
        super().__init__()
        logger.info("AKShareSource initialized")

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据

        AKShare的股票接口通常需要区分个股代码
        """
        if isinstance(symbol, list):
            # 批量获取
            dfs = []
            for s in symbol:
                df = self._get_single_stock_daily(s, start_date, end_date)
                if not df.empty:
                    dfs.append(df)
            return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        else:
            return self._get_single_stock_daily(symbol, start_date, end_date)

    def _get_single_stock_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取单只股票日频数据"""
        symbol = symbol.replace(".SZ", "").replace(".SH", "").replace(".", "")

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.strftime("%Y%m%d") if start_date else "19700101",
                end_date=end_date.strftime("%Y%m%d") if end_date else datetime.now().strftime("%Y%m%d"),
                adjust="qfq"  # 前复权
            )

            if df.empty:
                return df

            # 标准化列名
            df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "change_pct",
                "涨跌额": "change",
                "换手率": "turnover"
            }, inplace=True)

            df["symbol"] = self.normalize_symbol(symbol)
            df["date"] = pd.to_datetime(df["date"])

            return df

        except Exception as e:
            logger.warning(f"Failed to get data for {symbol}: {e}")
            return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级数据"""
        symbol = symbol.replace(".SZ", "").replace(".SH", "").replace(".", "")

        try:
            # AKShare的分钟数据接口
            period_map = {
                "1min": "1",
                "5min": "5",
                "15min": "15",
                "30min": "30",
                "60min": "60"
            }
            period = period_map.get(freq, "1")

            df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=period)

            if df.empty:
                return df

            df.rename(columns={
                "时间": "datetime",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount"
            }, inplace=True)

            df["symbol"] = self.normalize_symbol(symbol)
            df["datetime"] = pd.to_datetime(df["datetime"])

            return df

        except Exception as e:
            logger.warning(f"Failed to get minute data for {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取基本面数据"""
        # AKShare有多种财务数据接口，这里简化处理
        try:
            # 获取所有股票的财务指标
            df = ak.stock_financial_analysis_indicator(symbol="全部股票")

            if fields:
                available_cols = ["代码", "名称"] + fields
                df = df[[col for col in available_cols if col in df.columns]]

            df.rename(columns={
                "代码": "symbol",
                "名称": "name"
            }, inplace=True)

            if isinstance(symbol, str):
                symbol = [symbol]

            symbols = [s.replace(".SZ", "").replace(".SH", "") for s in symbol]
            df = df[df["symbol"].isin(symbols)]

            return df

        except Exception as e:
            logger.warning(f"Failed to get fundamentals: {e}")
            return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股"""
        # 将标准指数代码转换为AKShare格式
        index_map = {
            "000300.SH": "000300",
            "000905.SH": "000905",
            "000001.SH": "000001",
            "399001.SZ": "399001",
            "399006.SZ": "399006"
        }

        ak_code = index_map.get(index_code, index_code.replace(".SH", "").replace(".SZ", ""))

        try:
            df = ak.index_stock_cons(symbol=ak_code)
            return df["品种代码"].tolist() if "品种代码" in df.columns else []
        except Exception as e:
            logger.warning(f"Failed to get index components for {index_code}: {e}")
            return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历"""
        try:
            df = ak.tool_trade_date_hist_sina()
            df.rename(columns={"trade_date": "date"}, inplace=True)
            df["date"] = pd.to_datetime(df["date"])

            if start_date:
                df = df[df["date"] >= start_date]
            if end_date:
                df = df[df["date"] <= end_date]

            return df
        except Exception as e:
            logger.warning(f"Failed to get trade calendar: {e}")
            return pd.DataFrame()

    def get_stock_list(self, market: str = "A") -> pd.DataFrame:
        """获取股票列表

        Args:
            market: 市场，A=全部A股，SH=上海，SZ=深圳
        """
        try:
            if market == "A":
                df = ak.stock_zh_a_spot_em()
            elif market == "SH":
                df = ak.stock_sh_a_spot_em()
            elif market == "SZ":
                df = ak.stock_sz_a_spot_em()
            else:
                df = ak.stock_zh_a_spot_em()

            return df
        except Exception as e:
            logger.warning(f"Failed to get stock list: {e}")
            return pd.DataFrame()

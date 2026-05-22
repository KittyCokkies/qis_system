"""
万得Wind数据源

需要安装WindPy库（从Wind终端安装）
"""
from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
from loguru import logger

from data.base import DataSourceBase


class WindSource(DataSourceBase):
    """万得Wind数据源

    提供A股、港股、美股、基金、期货、期权等全市场数据
    需要Wind金融终端授权

    使用方法:
        1. 安装WindPy: 从Wind终端菜单 -> 量化 -> API接口 -> Python插件安装
        2. 启动Wind终端并保持登录
        3. 在代码中导入使用

    Attributes:
        w: WindPy对象
        is_connected: 是否已连接
    """

    supports_daily_price = True
    supports_minute_price = True
    supports_fundamentals = True
    supports_index_components = True
    supports_trade_calendar = True

    def __init__(self):
        super().__init__()
        self.w = None
        self.is_connected = False
        self._try_connect()

    def _try_connect(self):
        """尝试连接Wind"""
        try:
            from WindPy import w
            self.w = w
            result = w.start()
            if result.ErrorCode == 0:
                self.is_connected = True
                logger.info("WindPy connected successfully")
            else:
                logger.warning(f"WindPy connection failed: {result.Data}")
        except ImportError:
            logger.error("WindPy not installed. Please install from Wind terminal.")
        except Exception as e:
            logger.error(f"Failed to connect WindPy: {e}")

    def ensure_connected(self) -> bool:
        """确保连接状态"""
        if not self.is_connected and self.w:
            result = self.w.start()
            self.is_connected = (result.ErrorCode == 0)
        # 额外检查连接状态
        if self.is_connected and self.w:
            self.is_connected = self.w.isconnected()
        return self.is_connected

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据

        Args:
            symbol: Wind代码，如 "000001.SZ", "000300.SH"
            start_date: 开始日期
            end_date: 结束日期
            fields: 字段列表，None表示全部

        Returns:
            DataFrame with OHLCV data
        """
        if not self.ensure_connected():
            logger.error("WindPy not connected")
            return pd.DataFrame()

        if isinstance(symbol, list):
            symbol = ",".join(symbol)

        # 默认获取所有字段
        if fields is None:
            fields = ["open", "high", "low", "close", "volume", "amt"]
        field_str = ",".join(fields)

        start_str = start_date.strftime("%Y%m%d") if start_date else "ED-1Y"
        end_str = end_date.strftime("%Y%m%d") if end_date else datetime.now().strftime("%Y%m%d")

        try:
            result = self.w.wsd(symbol, field_str, start_str, end_str, "Fill=Previous")

            if result.ErrorCode != 0:
                logger.warning(f"Wind query failed: {result.Data}")
                return pd.DataFrame()

            # 构建DataFrame
            data = pd.DataFrame(result.Data, index=result.Fields, columns=result.Times).T
            data.index = pd.to_datetime(data.index)
            data.index.name = "date"

            # 标准化列名
            column_mapping = {
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "VOLUME": "volume",
                "AMT": "amount",
            }
            data.rename(columns=column_mapping, inplace=True)
            data["symbol"] = symbol

            return data

        except Exception as e:
            logger.error(f"Failed to get data from Wind: {e}")
            return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级数据"""
        if not self.ensure_connected():
            return pd.DataFrame()

        # Wind分钟数据
        bar_size = freq.replace("min", "")

        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S") if start_date else ""
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S") if end_date else ""

        try:
            result = self.w.wsi(symbol, "open,high,low,close,volume", start_str, end_str, f"BarSize={bar_size}")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            data = pd.DataFrame(result.Data, index=result.Fields, columns=result.Times).T
            data.index = pd.to_datetime(data.index)
            data.index.name = "datetime"

            return data

        except Exception as e:
            logger.error(f"Failed to get minute data from Wind: {e}")
            return pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取财务数据"""
        if not self.ensure_connected():
            return pd.DataFrame()

        if isinstance(symbol, list):
            symbol = ",".join(symbol)

        # Wind财务报表字段
        default_fields = ["eps_ttm", "bps", "roe", "roa", "grossprofitmargin", "netprofitmargin"]
        fields = fields or default_fields
        field_str = ",".join(fields)

        date_str = date.strftime("%Y%m%d") if date else datetime.now().strftime("%Y%m%d")

        try:
            result = self.w.wss(symbol, field_str, f"tradeDate={date_str};rptDate={date_str}")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            data = pd.DataFrame(result.Data, index=result.Fields, columns=[symbol]).T
            data.index.name = "symbol"

            return data

        except Exception as e:
            logger.error(f"Failed to get fundamentals from Wind: {e}")
            return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股"""
        if not self.ensure_connected():
            return []

        date_str = date.strftime("%Y%m%d") if date else datetime.now().strftime("%Y%m%d")

        try:
            result = self.w.wset("indexconstituent", f"date={date_str};windcode={index_code}")

            if result.ErrorCode != 0:
                return []

            # 返回成分股代码列表
            if result.Data and len(result.Data) > 0:
                return result.Data[0] if isinstance(result.Data[0], list) else []

            return []

        except Exception as e:
            logger.error(f"Failed to get index components from Wind: {e}")
            return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历"""
        if not self.ensure_connected():
            return pd.DataFrame()

        start_str = start_date.strftime("%Y%m%d") if start_date else "20000101"
        end_str = end_date.strftime("%Y%m%d") if end_date else datetime.now().strftime("%Y%m%d")

        try:
            result = self.w.tdays(start_str, end_str, f"TradingCalendar={market}")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            dates = result.Data[0] if result.Data else []
            return pd.DataFrame({"date": pd.to_datetime(dates)})

        except Exception as e:
            logger.error(f"Failed to get trade calendar from Wind: {e}")
            return pd.DataFrame()

    def get_option_chain(
        self,
        underlying: str,
        expiry: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期权链

        Args:
            underlying: 标的代码，如 "510300.SH"
            expiry: 到期日，None表示获取所有到期日

        Returns:
            期权链DataFrame
        """
        if not self.ensure_connected():
            return pd.DataFrame()

        try:
            # 获取期权合约列表
            result = self.w.wset("optionchain", f"underlying={underlying}")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            # 解析结果
            data = pd.DataFrame(dict(zip(result.Fields, result.Data)))

            if expiry:
                data = data[data["expire_date"] == expiry.strftime("%Y-%m-%d")]

            return data

        except Exception as e:
            logger.error(f"Failed to get option chain from Wind: {e}")
            return pd.DataFrame()

    def get_future_contracts(
        self,
        underlying: str,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货合约列表"""
        if not self.ensure_connected():
            return pd.DataFrame()

        try:
            result = self.w.wset("futurecontract", f"underlying={underlying}")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            return pd.DataFrame(dict(zip(result.Fields, result.Data)))

        except Exception as e:
            logger.error(f"Failed to get future contracts from Wind: {e}")
            return pd.DataFrame()

    def get_etf_list(self, market: str = "A") -> pd.DataFrame:
        """获取ETF列表"""
        if not self.ensure_connected():
            return pd.DataFrame()

        try:
            result = self.w.wset("sectorconstituent", f"sectorid=1000015513000000")

            if result.ErrorCode != 0:
                return pd.DataFrame()

            return pd.DataFrame(dict(zip(result.Fields, result.Data)))

        except Exception as e:
            logger.error(f"Failed to get ETF list from Wind: {e}")
            return pd.DataFrame()

    def __del__(self):
        """析构时关闭连接"""
        if self.w and self.is_connected:
            try:
                self.w.close()
                logger.info("WindPy connection closed")
            except:
                pass

"""
数据源管理器

按数据类型智能路由到对应的数据源
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum

import pandas as pd
from loguru import logger

from config import get_settings
from data.akshare_source import AKShareSource
from data.base import DataSourceBase
from data.cache import DataCache
from data.dolphindb_source import DolphinDBSource
from data.ftp_source import FTPSource
from data.swifquant_source import SwifquantSource
from data.tonglian_source import TonglianSource
from data.tushare_source import TushareSource
from data.wind_source import WindSource


class DataType(str, Enum):
    """数据类型枚举"""
    # 行情数据
    STOCK_DAILY = "stock_daily"           # 股票日频
    STOCK_MINUTE = "stock_minute"         # 股票分钟
    STOCK_TICK = "stock_tick"             # 股票tick
    FUTURE_DAILY = "future_daily"         # 期货日频
    OPTION_DAILY = "option_daily"         # 期权日频
    INDEX_DAILY = "index_daily"           # 指数日频

    # 基本面数据
    FINANCIAL_REPORT = "financial_report" # 财务报表
    STOCK_BASIC = "stock_basic"           # 股票基础信息
    INDEX_COMPONENT = "index_component"   # 指数成分股

    # 特色数据
    OPTION_GREEKS = "option_greeks"       # 期权希腊值
    DELTA_HEDGE = "delta_hedge"           # 对冲数据
    MACRO_DATA = "macro_data"             # 宏观数据
    INDUSTRY_DATA = "industry_data"       # 产业链数据
    RESEARCH_REPORT = "research_report"   # 研报数据

    # 工具数据
    TRADE_CALENDAR = "trade_calendar"     # 交易日历


class DataManager:
    """数据源管理器

    按数据类型智能路由到对应的数据源
    """

    def __init__(self):
        self.settings = get_settings()
        self.cache = DataCache()

        # 初始化所有数据源（懒加载）
        self._sources: Dict[str, Optional[Any]] = {
            "wind": None,
            "tonglian": None,
            "swifquant": None,
            "tushare": None,
            "akshare": None,
            "ftp": None,
            "dolphindb": None,
        }

        # 数据类型路由表：数据类型 -> 数据源名称列表（按优先级）
        self._router: Dict[DataType, List[str]] = {
            # 股票行情：通联优先，其次Wind/Tushare/AKShare
            DataType.STOCK_DAILY: ["tonglian", "wind", "tushare", "akshare"],
            DataType.STOCK_MINUTE: ["dolphindb", "wind", "tonglian"],
            DataType.STOCK_TICK: ["dolphindb", "wind"],

            # 期货期权：通联优先，其次swifquant（期权特色）
            DataType.FUTURE_DAILY: ["tonglian", "wind", "akshare"],
            DataType.OPTION_DAILY: ["tonglian", "swifquant", "wind"],

            # 期权希腊值：swifquant专属
            DataType.OPTION_GREEKS: ["swifquant"],
            DataType.DELTA_HEDGE: ["swifquant"],

            # 基本面：通联、Wind、Tushare
            DataType.FINANCIAL_REPORT: ["tonglian", "wind", "tushare"],
            DataType.STOCK_BASIC: ["tonglian", "tushare", "akshare"],
            DataType.INDEX_COMPONENT: ["tonglian", "wind", "tushare"],
            DataType.INDEX_DAILY: ["tonglian", "wind", "tushare", "akshare"],

            # 宏观产业链：Wind专属
            DataType.MACRO_DATA: ["wind"],
            DataType.INDUSTRY_DATA: ["wind"],
            DataType.RESEARCH_REPORT: ["wind"],

            # 交易日历：通联、Tushare
            DataType.TRADE_CALENDAR: ["tonglian", "tushare"],
        }

        logger.info("DataManager initialized with type-based routing")

    def _get_source(self, name: str) -> Optional[Any]:
        """获取数据源（懒加载）"""
        if name not in self._sources:
            return None

        if self._sources[name] is None:
            try:
                if name == "wind":
                    self._sources[name] = WindSource()
                elif name == "tonglian":
                    self._sources[name] = TonglianSource()
                elif name == "swifquant":
                    self._sources[name] = SwifquantSource()
                elif name == "tushare":
                    self._sources[name] = TushareSource()
                elif name == "akshare":
                    self._sources[name] = AKShareSource()
                elif name == "ftp":
                    self._sources[name] = FTPSource()
                elif name == "dolphindb":
                    self._sources[name] = DolphinDBSource()

                logger.info(f"Initialized {name} source")

            except Exception as e:
                logger.warning(f"Failed to initialize {name} source: {e}")
                self._sources[name] = None

        return self._sources[name]

    def _route(
        self,
        data_type: DataType,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        按数据类型路由到对应数据源

        Args:
            data_type: 数据类型
            method_name: 要调用的方法名
            *args, **kwargs: 传递给方法的参数

        Returns:
            查询结果
        """
        source_names = self._router.get(data_type, [])

        if not source_names:
            logger.error(f"No data source registered for type: {data_type}")
            return None

        # 按优先级尝试各数据源
        for source_name in source_names:
            source = self._get_source(source_name)

            if source is None:
                continue

            try:
                method = getattr(source, method_name, None)
                if method is None:
                    logger.debug(f"{source_name} has no method {method_name}")
                    continue

                result = method(*args, **kwargs)

                # 检查结果是否有效
                if isinstance(result, pd.DataFrame) and not result.empty:
                    logger.info(f"Got {data_type.value} from {source_name}: {len(result)} rows")
                    return result
                elif isinstance(result, list) and result:
                    logger.info(f"Got {data_type.value} from {source_name}: {len(result)} items")
                    return result
                elif result is not None:
                    return result

            except Exception as e:
                logger.warning(f"Failed to get {data_type.value} from {source_name}: {e}")
                continue

        logger.error(f"Failed to get {data_type.value} from all sources: {source_names}")
        return None if not args else pd.DataFrame() if isinstance(args[0], str) else []

    # ==================== 行情数据接口 ====================

    def get_stock_daily(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取股票日频数据"""
        return self._route(
            DataType.STOCK_DAILY,
            "get_daily_price",
            symbol, start_date, end_date, fields
        )
        return result if result is not None and not (isinstance(result, pd.DataFrame) and result.empty) else pd.DataFrame()

    def get_stock_minute(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取股票分钟数据"""
        return self._route(
            DataType.STOCK_MINUTE,
            "get_minute_price",
            symbol, start_date, end_date, freq
        ) or pd.DataFrame()

    def get_future_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货日频数据"""
        return self._route(
            DataType.FUTURE_DAILY,
            "get_future_daily",
            symbol, start_date, end_date
        ) or pd.DataFrame()

    def get_option_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期权日频数据"""
        return self._route(
            DataType.OPTION_DAILY,
            "get_option_daily",
            symbol, start_date, end_date
        ) or pd.DataFrame()

    # ==================== 期权特色数据（swifquant专属） ====================

    def get_option_greeks(
        self,
        symbol: str,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        获取期权希腊值

        专属数据源：swifquant
        表：ads_deltahedge_contract_greeks
        """
        swifquant = self._get_source("swifquant")
        if swifquant is None:
            logger.error("Swifquant source not available")
            return pd.DataFrame()

        try:
            # 使用原始查询，后续可根据实际表结构调整
            date_str = date.strftime("%Y-%m-%d") if date else "CURDATE()"
            sql = f"""
                SELECT * FROM ads_deltahedge_contract_greeks
                WHERE trade_date = '{date_str}'
                AND underlying_code = '{symbol}'
                LIMIT 1000
            """
            return swifquant.raw_query(sql)
        except Exception as e:
            logger.error(f"Failed to get option greeks: {e}")
            return pd.DataFrame()

    def get_delta_hedge_data(
        self,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        获取Delta对冲数据

        专属数据源：swifquant
        表：ads_deltahedge_sumgreeks 或 daily_position_adjust
        """
        swifquant = self._get_source("swifquant")
        if swifquant is None:
            logger.error("Swifquant source not available")
            return pd.DataFrame()

        try:
            date_str = date.strftime("%Y-%m-%d") if date else "CURDATE()"
            sql = f"""
                SELECT * FROM ads_deltahedge_sumgreeks
                WHERE trade_date = '{date_str}'
                LIMIT 1000
            """
            return swifquant.raw_query(sql)
        except Exception as e:
            logger.error(f"Failed to get delta hedge data: {e}")
            return pd.DataFrame()

    # ==================== 基本面数据接口 ====================

    def get_financial_report(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取财务报表数据"""
        return self._route(
            DataType.FINANCIAL_REPORT,
            "get_fundamentals",
            symbol, fields, date
        ) or pd.DataFrame()

    def get_index_components(
        self,
        index_code: str,
        date: Optional[datetime] = None
    ) -> List[str]:
        """获取指数成分股"""
        return self._route(
            DataType.INDEX_COMPONENT,
            "get_index_components",
            index_code, date
        ) or []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历"""
        return self._route(
            DataType.TRADE_CALENDAR,
            "get_trade_calendar",
            start_date, end_date, market
        ) or pd.DataFrame()

    # ==================== Wind专属数据接口 ====================

    def get_macro_data(
        self,
        indicator: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        获取宏观数据

        专属数据源：Wind
        """
        wind = self._get_source("wind")
        if wind is None or not wind.is_connected:
            logger.error("Wind source not available")
            return pd.DataFrame()

        try:
            # Wind有专门的宏观数据接口
            return wind.get_macro_data(indicator, start_date, end_date)
        except Exception as e:
            logger.error(f"Failed to get macro data: {e}")
            return pd.DataFrame()

    def get_industry_chain(
        self,
        industry: str
    ) -> pd.DataFrame:
        """
        获取产业链数据

        专属数据源：Wind
        """
        wind = self._get_source("wind")
        if wind is None or not wind.is_connected:
            logger.error("Wind source not available")
            return pd.DataFrame()

        try:
            return wind.get_industry_chain(industry)
        except Exception as e:
            logger.error(f"Failed to get industry chain: {e}")
            return pd.DataFrame()

    # ==================== 通用查询接口 ====================

    def query(
        self,
        data_type: Union[DataType, str],
        **kwargs
    ) -> Any:
        """
        通用查询接口

        Args:
            data_type: 数据类型（可用字符串或DataType枚举）
            **kwargs: 查询参数

        Returns:
            查询结果
        """
        if isinstance(data_type, str):
            data_type = DataType(data_type)

        # 根据数据类型分发到具体方法
        method_map = {
            DataType.STOCK_DAILY: self.get_stock_daily,
            DataType.STOCK_MINUTE: self.get_stock_minute,
            DataType.FUTURE_DAILY: self.get_future_daily,
            DataType.OPTION_DAILY: self.get_option_daily,
            DataType.OPTION_GREEKS: self.get_option_greeks,
            DataType.DELTA_HEDGE: self.get_delta_hedge_data,
            DataType.FINANCIAL_REPORT: self.get_financial_report,
            DataType.INDEX_COMPONENT: self.get_index_components,
            DataType.TRADE_CALENDAR: self.get_trade_calendar,
            DataType.MACRO_DATA: self.get_macro_data,
        }

        method = method_map.get(data_type)
        if method:
            return method(**kwargs)
        else:
            logger.error(f"Unknown data type: {data_type}")
            return pd.DataFrame()

    def raw_query(
        self,
        source_name: str,
        sql: str
    ) -> pd.DataFrame:
        """
        对指定数据源执行原始SQL查询

        用于探索性查询或临时需求

        Args:
            source_name: 数据源名称（swifquant/tonglian/wind等）
            sql: SQL查询语句
        """
        source = self._get_source(source_name)
        if source is None:
            logger.error(f"Source {source_name} not available")
            return pd.DataFrame()

        if hasattr(source, 'raw_query'):
            return source.raw_query(sql)
        elif hasattr(source, '_execute_query'):
            return source._execute_query(sql)
        else:
            logger.error(f"Source {source_name} does not support raw query")
            return pd.DataFrame()

    # ==================== 管理接口 ====================

    def get_data_availability(self) -> Dict[str, bool]:
        """获取各数据源可用状态"""
        status = {}
        for name in self._sources.keys():
            source = self._get_source(name)
            status[name] = source is not None
        return status

    def get_router_config(self) -> Dict[str, List[str]]:
        """获取当前路由配置"""
        return {k.value: v for k, v in self._router.items()}

    def set_route(
        self,
        data_type: Union[DataType, str],
        source_priority: List[str]
    ):
        """
        自定义某数据类型的路由优先级

        Args:
            data_type: 数据类型
            source_priority: 数据源优先级列表
        """
        if isinstance(data_type, str):
            data_type = DataType(data_type)

        self._router[data_type] = source_priority
        logger.info(f"Updated route for {data_type.value}: {source_priority}")

    def clear_cache(self):
        """清除所有缓存"""
        self.cache.invalidate()
        logger.info("Cache cleared")

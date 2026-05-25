"""
数据源管理器

按数据类型智能路由到对应的数据源，支持本地缓存和持久化
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum

import pandas as pd
from loguru import logger

from config import get_settings
from data.akshare_source import AKShareSource
from data.base import DataSourceBase
from data.cache import DataCache
from data.database import DatabaseManager
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

    核心设计原则：
    1. 策略只读本地数据（PostgreSQL/DolphinDB），保证速度
    2. 数据同步在收盘后批量执行，从远程获取写入本地
    3. 热数据（今日）可配置从远程实时获取或延迟到本地同步
    4. 多源数据自动校验和填充

    使用方式：
        # 策略中使用（只读本地，极快）
        dm = DataManager()
        df = dm.get_daily_price(['000001.SZ'], start='2024-01-01', end='2024-12-31')

        # 收盘后同步（从远程更新本地）
        dm.sync_daily_price(['000001.SZ'], date='2024-12-31')
    """

    def __init__(
        self,
        use_local_first: bool = True,      # 优先从本地读取
        use_cache: bool = True,            # 启用内存缓存
        hot_data_window: int = 0,          # 热数据窗口（天数），0表示全部本地
    ):
        self.settings = get_settings()
        self.use_local_first = use_local_first
        self.use_cache = use_cache
        self.hot_data_window = hot_data_window

        # 本地存储
        self.local_db = DatabaseManager()

        # 内存缓存
        self.cache = DataCache() if use_cache else None

        # 远程数据源（懒加载）
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

        logger.info(f"DataManager initialized: local_first={use_local_first}, cache={use_cache}")

    # ==================== 核心读取接口（策略使用） ====================

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        fields: Optional[List[str]] = None,
        use_remote: bool = False,  # 强制从远程获取（数据同步时用）
    ) -> pd.DataFrame:
        """获取日频行情数据（策略主入口）

        默认从本地PostgreSQL读取，速度极快。
        如果本地没有，自动从远程获取并缓存到本地。

        Args:
            symbol: 标的代码或列表，如 '000001.SZ' 或 ['000001.SZ', '000002.SZ']
            start_date: 开始日期
            end_date: 结束日期
            fields: 需要的字段，None表示全部
            use_remote: 强制从远程获取（数据同步时用）

        Returns:
            DataFrame with columns: [symbol, date, open, high, low, close, volume, ...]

        Example:
            >>> dm = DataManager()
            >>> df = dm.get_daily_price('000001.SZ', '2024-01-01', '2024-12-31')
            >>> df = dm.get_daily_price(['000001.SZ', '000002.SZ'])  # 批量获取
        """
        # 标准化日期
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        # 检查是否需要从远程获取（热数据窗口）
        is_hot_data = self._is_hot_data(end_date)

        if not use_remote and self.use_local_first and not is_hot_data:
            # 优先从本地读取
            df = self.local_db.get_daily_price(symbol, start_date, end_date, fields)
            if not df.empty:
                logger.debug(f"Got {len(df)} rows from local DB")
                return df
            logger.info("Local data not found, fetching from remote...")

        # 从远程获取
        df = self._fetch_from_remote(
            DataType.STOCK_DAILY,
            "get_daily_price",
            symbol, start_date, end_date, fields
        )

        # 保存到本地（供下次快速读取）
        if not df.empty and not is_hot_data:
            self.local_db.save_daily_price(df)
            logger.info(f"Saved {len(df)} rows to local DB")

        return df

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min",
        use_remote: bool = False,
    ) -> pd.DataFrame:
        """获取分钟级数据

        高频数据建议存储在DolphinDB中，查询速度更快。
        """
        if self.use_local_first and not use_remote:
            # 尝试从DolphinDB读取
            ddb = self._get_source("dolphindb")
            if ddb and ddb.is_connected:
                df = ddb.get_minute_price(symbol, start_date, end_date, freq)
                if not df.empty:
                    return df

        return self._fetch_from_remote(
            DataType.STOCK_MINUTE,
            "get_minute_price",
            symbol, start_date, end_date, freq
        ) or pd.DataFrame()

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None,
        use_remote: bool = False,
    ) -> pd.DataFrame:
        """获取基本面/财务数据"""
        # 财务数据更新频率低，优先本地
        if self.use_local_first and not use_remote:
            # TODO: 实现本地财务数据表
            pass

        return self._fetch_from_remote(
            DataType.FINANCIAL_REPORT,
            "get_fundamentals",
            symbol, fields, date
        ) or pd.DataFrame()

    def get_index_components(
        self,
        index_code: str,
        date: Optional[datetime] = None,
        use_remote: bool = False,
    ) -> List[str]:
        """获取指数成分股"""
        if self.use_local_first and not use_remote:
            # TODO: 实现本地成分股表
            pass

        return self._fetch_from_remote(
            DataType.INDEX_COMPONENT,
            "get_index_components",
            index_code, date
        ) or []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE",
        use_remote: bool = False,
    ) -> pd.DataFrame:
        """获取交易日历"""
        # 日历数据可长期缓存
        cache_key = f"calendar_{market}_{start_date}_{end_date}"
        if self.cache and not use_remote:
            cached = self.cache.get(cache_key, max_age_hours=168)  # 7天
            if cached is not None:
                return cached

        df = self._fetch_from_remote(
            DataType.TRADE_CALENDAR,
            "get_trade_calendar",
            start_date, end_date, market
        ) or pd.DataFrame()

        if self.cache and not df.empty:
            self.cache.set(cache_key, df)

        return df

    # ==================== 数据同步接口（收盘后使用） ====================

    def sync_daily_price(
        self,
        symbols: Union[str, List[str]],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        source_priority: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """同步日频数据到本地存储

        收盘后执行，从远程数据源获取最新数据写入本地PostgreSQL。
        支持增量同步（只获取缺失的数据）。

        Args:
            symbols: 标的代码或列表
            start_date: 开始日期，None表示从上次同步日期继续
            end_date: 结束日期，None表示今天
            source_priority: 数据源优先级，None使用默认路由

        Returns:
            同步统计 {symbol: 新增行数}

        Example:
            >>> dm = DataManager()
            >>> # 同步单只股票
            >>> dm.sync_daily_price('000001.SZ', '2024-01-01', '2024-12-31')
            >>> # 同步股票列表
            >>> universe = dm.get_index_components('000300.SH')
            >>> dm.sync_daily_price(universe)  # 同步沪深300全成分股
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        if end_date is None:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')

        stats = {}

        for symbol in symbols:
            try:
                # 检查本地已有数据
                if start_date is None:
                    local_latest = self._get_local_latest_date(symbol)
                    if local_latest:
                        sync_start = local_latest + timedelta(days=1)
                    else:
                        sync_start = end_date - timedelta(days=365*5)  # 默认5年
                else:
                    sync_start = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else start_date

                if sync_start > end_date:
                    logger.debug(f"{symbol} already up to date")
                    stats[symbol] = 0
                    continue

                # 从远程获取
                df = self.get_daily_price(
                    symbol,
                    sync_start,
                    end_date,
                    use_remote=True  # 强制远程
                )

                if not df.empty:
                    # 保存到本地
                    saved = self.local_db.save_daily_price(df)
                    stats[symbol] = len(df) if saved else 0
                    logger.info(f"Synced {symbol}: {len(df)} rows from {sync_start.date()} to {end_date.date()}")
                else:
                    stats[symbol] = 0
                    logger.warning(f"No data for {symbol}")

            except Exception as e:
                logger.error(f"Failed to sync {symbol}: {e}")
                stats[symbol] = -1

        return stats

    def sync_index_components(
        self,
        index_code: str = "000300.SH",
        date: Optional[datetime] = None,
    ) -> List[str]:
        """同步指数成分股

        获取最新成分股列表并保存到本地，用于构建股票池。
        """
        components = self.get_index_components(index_code, date, use_remote=True)

        if components:
            # 保存到本地
            df = pd.DataFrame({
                'index_code': index_code,
                'symbol': components,
                'date': date or datetime.now(),
            })
            # TODO: 实现本地成分股表保存
            logger.info(f"Synced {index_code} components: {len(components)} stocks")

        return components

    # ==================== 股票池/ Universe 管理 ====================

    def get_universe(
        self,
        index_code: Optional[str] = "000300.SH",
        date: Optional[datetime] = None,
        include_st: bool = False,
        min_listing_days: int = 60,
    ) -> List[str]:
        """获取股票池

        策略开发的标准入口，获取可交易的股票列表。

        Args:
            index_code: 指数代码作为基础池，None表示全市场
            date: 查询日期
            include_st: 是否包含ST股票
            min_listing_days: 最小上市天数

        Returns:
            标的代码列表
        """
        if index_code:
            symbols = self.get_index_components(index_code, date)
        else:
            # TODO: 获取全市场股票
            symbols = []

        # TODO: 过滤ST、次新股等

        return symbols

    # ==================== 内部方法 ====================

    def _is_hot_data(self, date: datetime) -> bool:
        """检查是否是热数据（在热数据窗口内）"""
        if self.hot_data_window <= 0:
            return False
        return (datetime.now() - date).days <= self.hot_data_window

    def _get_local_latest_date(self, symbol: str) -> Optional[datetime]:
        """获取本地数据的最新日期"""
        try:
            df = self.local_db.get_daily_price(symbol, fields=['date'])
            if not df.empty:
                return df['date'].max()
        except Exception:
            pass
        return None

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

    def _fetch_from_remote(
        self,
        data_type: DataType,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """从远程数据源获取数据"""
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
        return None

    # ==================== 管理接口 ====================

    def get_data_availability(self) -> Dict[str, bool]:
        """获取各数据源可用状态"""
        status = {}
        for name in self._sources.keys():
            source = self._get_source(name)
            status[name] = source is not None
        return status

    def set_route(
        self,
        data_type: Union[DataType, str],
        source_priority: List[str]
    ):
        """自定义某数据类型的路由优先级"""
        if isinstance(data_type, str):
            data_type = DataType(data_type)

        self._router[data_type] = source_priority
        logger.info(f"Updated route for {data_type.value}: {source_priority}")

    def clear_cache(self):
        """清除所有缓存"""
        if self.cache:
            self.cache.invalidate()
        logger.info("Cache cleared")

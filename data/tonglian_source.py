"""
通联数据数据库源

通过MySQL直接连接通联数据库 (DataYes)
"""
from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
import pymysql
from loguru import logger
from sqlalchemy import create_engine, text

from config import get_settings
from data.base import DataSourceBase


class TonglianSource(DataSourceBase):
    """通联数据库数据源

    通过SQL直连通联MySQL数据库获取数据
    支持：日频行情、财务数据、指数成分、交易日历

    Attributes:
        engine: SQLAlchemy引擎
        conn: 数据库连接
    """

    supports_daily_price = True
    supports_minute_price = False  # 暂不支持分钟数据
    supports_fundamentals = True
    supports_index_components = True
    supports_trade_calendar = True

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.engine = None
        self._connect()

    def _connect(self):
        """建立数据库连接"""
        try:
            config = self.settings.tonglian

            # 使用 pymysql 直接连接（避免 SQLAlchemy URL 解析问题）
            import pymysql
            self._conn_params = {
                'host': config.host,
                'port': config.port,
                'user': config.user,
                'password': config.password,
                'database': config.database,
                'charset': config.charset,
            }

            # 测试连接
            test_conn = pymysql.connect(**self._conn_params)
            test_conn.close()

            # 创建 SQLAlchemy 引擎（使用 pymysql 直接传参）
            from sqlalchemy import create_engine
            self.engine = create_engine(
                "mysql+pymysql://",
                creator=lambda: pymysql.connect(**self._conn_params),
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600
            )

            logger.info(f"Tonglian database connected: {config.host}:{config.port}/{config.database}")

        except Exception as e:
            logger.error(f"Failed to connect Tonglian database: {e}")
            self.engine = None

    def _execute_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行SQL查询"""
        if not self.engine:
            logger.error("Database not connected")
            return pd.DataFrame()

        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params)
        except Exception as e:
            logger.error(f"Query failed: {e}\nSQL: {sql}")
            return pd.DataFrame()

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频行情数据

        表: mkt_equd (股票日行情), mkt_futd (期货日行情), mkt_optd (期权日行情)
        """
        if isinstance(symbol, str):
            symbol = [symbol]

        # 移除后缀，通联使用纯代码
        symbols = [s.replace(".SH", "").replace(".SZ", "").replace(".CF", "").replace(".CFE", "") for s in symbol]
        symbol_str = "','".join(symbols)

        # 字段映射（根据通联实际表结构调整）
        field_mapping = {
            "open": "OPEN_PRICE",
            "high": "HIGHEST_PRICE",
            "low": "LOWEST_PRICE",
            "close": "CLOSE_PRICE",
            "volume": "TURNOVER_VOL",
            "amount": "TURNOVER_VALUE",
            "pre_close": "PRE_CLOSE_PRICE",
            "change_pct": "CHG_PCT",  # 涨跌幅
        }

        if fields:
            select_fields = [field_mapping.get(f, f) for f in fields]
        else:
            select_fields = list(field_mapping.values())

        field_str = ",".join(select_fields)

        sql = f"""
            SELECT
                TICKER_SYMBOL as symbol,
                TRADE_DATE as date,
                {field_str}
            FROM mkt_equd
            WHERE TICKER_SYMBOL IN ('{symbol_str}')
        """

        if start_date:
            sql += f" AND TRADE_DATE >= '{start_date.strftime('%Y-%m-%d')}'"
        if end_date:
            sql += f" AND TRADE_DATE <= '{end_date.strftime('%Y-%m-%d')}'"

        sql += " ORDER BY TRADE_DATE"

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            # 标准化列名
            reverse_mapping = {v: k for k, v in field_mapping.items()}
            df.rename(columns=reverse_mapping, inplace=True)
            # 添加标准化后缀
            df["symbol"] = df["symbol"].apply(lambda x: f"{x}.SH" if str(x).startswith("6") else f"{x}.SZ")

        return df

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取财务数据

        表: fdmt_xxx (财务报表系列)
        """
        if isinstance(symbol, str):
            symbol = [symbol]

        symbols = [s.replace(".SH", "").replace(".SZ", "") for s in symbol]
        symbol_str = "','".join(symbols)

        # 常用财务字段
        field_mapping = {
            "eps": "BASIC_EPS",
            "bps": "BPS",
            "roe": "ROE",
            "roa": "ROA",
            "gross_margin": "GROSS_PROFIT_MARGIN",
            "net_margin": "NET_PROFIT_MARGIN",
            "revenue": "TOT_OPER_REV",
            "net_income": "NET_PROFIT",
            "total_assets": "TOT_ASSETS",
            "equity": "TOT_EQUITY",
        }

        if fields:
            select_fields = [field_mapping.get(f, f) for f in fields]
        else:
            select_fields = list(field_mapping.values())

        field_str = ",".join(select_fields)

        report_date = date.strftime("%Y-%m-%d") if date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                SECURITY_ID as symbol,
                END_DATE as report_date,
                {field_str}
            FROM fdmt_main_data
            WHERE SECURITY_ID IN ('{symbol_str}')
            AND END_DATE <= '{report_date}'
            AND REPORT_TYPE = 'A'  -- 年报
            ORDER BY END_DATE DESC
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["report_date"] = pd.to_datetime(df["report_date"])
            reverse_mapping = {v: k for k, v in field_mapping.items()}
            df.rename(columns=reverse_mapping, inplace=True)

        return df

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股

        表: idx_cons (指数成分)
        """
        # 移除后缀
        index_code = index_code.replace(".SH", "").replace(".SZ", "")

        query_date = date.strftime("%Y-%m-%d") if date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                CONS_ID as symbol
            FROM idx_cons
            WHERE INDEX_ID = '{index_code}'
            AND TRADE_DATE = (
                SELECT MAX(TRADE_DATE)
                FROM idx_cons
                WHERE INDEX_ID = '{index_code}'
                AND TRADE_DATE <= '{query_date}'
            )
        """

        df = self._execute_query(sql)

        if not df.empty:
            return df["symbol"].tolist()
        return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历

        表: md_calendar
        """
        start_str = start_date.strftime("%Y-%m-%d") if start_date else "2000-01-01"
        end_str = end_date.strftime("%Y-%m-%d") if end_date else datetime.now().strftime("%Y-%m-%d")

        exchange_map = {
            "SSE": "XSHG",  # 上交所
            "SZSE": "XSHE",  # 深交所
        }
        exchange = exchange_map.get(market, "XSHG")

        sql = f"""
            SELECT
                CALENDAR_DATE as date,
                IS_OPEN as is_trading_day
            FROM md_calendar
            WHERE EXCHANGE_CD = '{exchange}'
            AND CALENDAR_DATE BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY CALENDAR_DATE
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["is_trading_day"] = df["is_trading_day"] == 1

        return df

    def get_stock_list(self, market: str = "A") -> pd.DataFrame:
        """获取股票列表

        表: sec_main (证券主表)
        """
        exchange_map = {
            "A": "XSHG,XSHE",
            "SH": "XSHG",
            "SZ": "XSHE",
        }
        exchanges = exchange_map.get(market, "XSHG,XSHE")

        sql = f"""
            SELECT
                SECURITY_ID as symbol,
                SECURITY_NAME_ABBR as name,
                LIST_DATE as list_date,
                DELIST_DATE as delist_date
            FROM sec_main
            WHERE EXCHANGE_CD IN ('{exchanges}')
            AND ASSET_CLASS = 'E'  -- 股票
            AND DELIST_DATE IS NULL  -- 未退市
        """

        return self._execute_query(sql)

    def get_future_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货日行情

        表: mkt_futd
        """
        start_str = start_date.strftime("%Y-%m-%d") if start_date else "2000-01-01"
        end_str = end_date.strftime("%Y-%m-%d") if end_date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                SECURITY_ID as symbol,
                TRADE_DATE as date,
                OPEN_PRICE as open,
                HIGH_PRICE as high,
                LOW_PRICE as low,
                CLOSE_PRICE as close,
                TURNOVER_VOL as volume,
                TURNOVER_VALUE as amount,
                OPEN_INTEREST as open_interest,
                SETTLEMENT_PRICE as settlement
            FROM mkt_futd
            WHERE SECURITY_ID = '{symbol}'
            AND TRADE_DATE BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY TRADE_DATE
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])

        return df

    def get_option_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期权日行情

        表: mkt_optd
        """
        start_str = start_date.strftime("%Y-%m-%d") if start_date else "2000-01-01"
        end_str = end_date.strftime("%Y-%m-%d") if end_date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                SECURITY_ID as symbol,
                TRADE_DATE as date,
                OPEN_PRICE as open,
                HIGH_PRICE as high,
                LOW_PRICE as low,
                CLOSE_PRICE as close,
                TURNOVER_VOL as volume,
                TURNOVER_VALUE as amount,
                OPEN_INTEREST as open_interest,
                PRE_SETTLEMENT_PRICE as pre_settlement,
                SETTLEMENT_PRICE as settlement,
                EXERCISE_PRICE as strike,
                EXPIRE_DATE as expiry
            FROM mkt_optd
            WHERE SECURITY_ID = '{symbol}'
            AND TRADE_DATE BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY TRADE_DATE
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["expiry"] = pd.to_datetime(df["expiry"])

        return df

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级数据

        通联分钟数据通常存储在不同的表中，这里提供基本框架
        """
        logger.warning("Tonglian minute data not yet implemented")
        return pd.DataFrame()

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM sec_main LIMIT 1"))
                count = result.scalar()
                logger.info(f"Tonglian connection test passed. Sample count: {count}")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

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
            from sqlalchemy import text
            # 使用 SQLAlchemy 的 execute 方法
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                # 转换为 DataFrame
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df
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

        # 字段映射（通联实际字段名 - 下划线大写格式）
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
            "eps": "BasicEPS",
            "bps": "BPS",
            "roe": "ROE",
            "roa": "ROA",
            "gross_margin": "GrossProfitMargin",
            "net_margin": "NetProfitMargin",
            "revenue": "TotOperRev",
            "net_income": "NetProfit",
            "total_assets": "TotAssets",
            "equity": "TotEquity",
        }

        if fields:
            select_fields = [field_mapping.get(f, f) for f in fields]
        else:
            select_fields = list(field_mapping.values())

        field_str = ",".join(select_fields)

        report_date = date.strftime("%Y-%m-%d") if date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                TickerSymbol as symbol,
                EndDate as report_date,
                {field_str}
            FROM fdmt_main_data
            WHERE TickerSymbol IN ('{symbol_str}')
            AND EndDate <= '{report_date}'
            AND ReportType = 'A'  -- 年报
            ORDER BY EndDate DESC
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
                ConsTickerSymbol as symbol
            FROM idx_cons
            WHERE IndexTickerSymbol = '{index_code}'
            AND TradeDate = (
                SELECT MAX(TradeDate)
                FROM idx_cons
                WHERE IndexTickerSymbol = '{index_code}'
                AND TradeDate <= '{query_date}'
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
                CalendarDate as date,
                IsOpen as is_trading_day
            FROM md_calendar
            WHERE ExchangeCode = '{exchange}'
            AND CalendarDate BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY CalendarDate
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
                TickerSymbol as symbol,
                ShortName as name,
                ListDate as list_date,
                DelistDate as delist_date
            FROM sec_equity
            WHERE ExchangeCode IN ('{exchanges}')
            AND DelistDate IS NULL  -- 未退市
        """

        return self._execute_query(sql)

    def get_future_daily(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货日行情

        表: mkt_futd (期货日行情表)
        关键字段: TICKER_SYMBOL(合约代码), TRADE_DATE(交易日期), CONTRACT_OBJECT(品种)
        """
        start_str = start_date.strftime("%Y-%m-%d") if start_date else "2000-01-01"
        end_str = end_date.strftime("%Y-%m-%d") if end_date else datetime.now().strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                TICKER_SYMBOL as symbol,
                TRADE_DATE as date,
                OPEN_PRICE as open,
                HIGHEST_PRICE as high,
                LOWEST_PRICE as low,
                CLOSE_PRICE as close,
                SETTL_PRICE as settle,
                TURNOVER_VOL as volume,
                TURNOVER_VALUE as amount,
                OPEN_INT as open_interest,
                LAST_TRADE_DATE as expiry_date,
                MAINCON as is_main_contract,
                SMAINCON as is_sub_main_contract
            FROM mkt_futd
            WHERE TICKER_SYMBOL = '{symbol}'
            AND TRADE_DATE BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY TRADE_DATE
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["expiry_date"] = pd.to_datetime(df["expiry_date"])

        return df

    def get_future_contracts(
        self,
        contract_object: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货合约列表及基本信息

        从 mkt_futd 表中提取合约信息，包含 CONTRACT_OBJECT, TICKER_SYMBOL, LAST_TRADE_DATE
        """
        sql = f"""
            SELECT DISTINCT
                TICKER_SYMBOL as symbol,
                CONTRACT_OBJECT as underlying,
                LAST_TRADE_DATE as last_trade_date,
                EXCHANGE_CD as exchange
            FROM mkt_futd
            WHERE CONTRACT_OBJECT = '{contract_object}'
        """

        if start_date:
            sql += f" AND LAST_TRADE_DATE >= '{start_date.strftime('%Y-%m-%d')}'"
        if end_date:
            sql += f" AND LAST_TRADE_DATE <= '{end_date.strftime('%Y-%m-%d')}'"

        sql += " ORDER BY LAST_TRADE_DATE"

        df = self._execute_query(sql)

        if not df.empty:
            df["last_trade_date"] = pd.to_datetime(df["last_trade_date"])

        return df

    def get_contract_details(
        self,
        contract_object: str
    ) -> pd.DataFrame:
        """从 futu 表获取期货合约详细信息

        表: futu (期货合约信息表)
        关键字段:
            TICKER_SYMBOL - 合约代码
            CONT_MULT_NUM - 合约乘数
            MIN_CHG_PRICE_NUM - 最小变动价位
            LIST_DATE - 上市日期
            LAST_TRADE_DATE - 最后交易日
            DELI_YEAR/DELI_MONTH - 交割年月

        Args:
            contract_object: 品种代码，如 'IF', 'RB'

        Returns:
            DataFrame with columns:
                symbol, multiplier, tick_size, list_date, last_trade_date,
                deli_year, deli_month, contract_month, exchange
        """
        sql = f"""
            SELECT DISTINCT
                TICKER_SYMBOL as symbol,
                CONT_MULT_NUM as multiplier,
                MIN_CHG_PRICE_NUM as tick_size,
                LIST_DATE as list_date,
                LAST_TRADE_DATE as last_trade_date,
                DELI_YEAR as deli_year,
                DELI_MONTH as deli_month,
                EXCHANGE_CD as exchange
            FROM futu
            WHERE CONTRACT_OBJECT = '{contract_object}'
            ORDER BY LIST_DATE
        """

        df = self._execute_query(sql)

        if not df.empty:
            # 去重（以防万一）
            df = df.drop_duplicates(subset=['symbol'])

            # 转换日期格式
            df['list_date'] = pd.to_datetime(df['list_date'])
            df['last_trade_date'] = pd.to_datetime(df['last_trade_date'])

            # 构建合约月份 (如 202401)
            df['contract_month'] = df['deli_year'].astype(str).str.replace('.0', '', regex=False) + \
                                   df['deli_month'].astype(int).astype(str).str.zfill(2)

            # 标准化交易所代码
            exchange_map = {
                'XSHG': 'SSE',      # 上交所
                'XSHE': 'SZSE',     # 深交所
                'CCFX': 'CFFEX',    # 中金所
                'XSGE': 'SHFE',     # 上期所
                'XDCE': 'DCE',      # 大商所
                'XZCE': 'CZCE',     # 郑商所
                'XINE': 'INE',      # 上期能源
            }
            df['exchange'] = df['exchange'].map(exchange_map).fillna(df['exchange'])

        return df

    def get_contracts_by_date(
        self,
        contract_object: str,
        trade_date: datetime
    ) -> pd.DataFrame:
        """获取某品种在特定日期的所有合约数据

        表: mkt_futd
        """
        date_str = trade_date.strftime("%Y-%m-%d")

        sql = f"""
            SELECT
                TICKER_SYMBOL as symbol,
                TRADE_DATE as date,
                OPEN_PRICE as open,
                HIGHEST_PRICE as high,
                LOWEST_PRICE as low,
                CLOSE_PRICE as close,
                SETTL_PRICE as settle,
                TURNOVER_VOL as volume,
                TURNOVER_VALUE as amount,
                OPEN_INT as open_interest,
                LAST_TRADE_DATE as expiry_date,
                MAINCON as is_main_contract,
                SMAINCON as is_sub_main_contract
            FROM mkt_futd
            WHERE CONTRACT_OBJECT = '{contract_object}'
            AND TRADE_DATE = '{date_str}'
            ORDER BY TICKER_SYMBOL
        """

        df = self._execute_query(sql)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["expiry_date"] = pd.to_datetime(df["expiry_date"])

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
                TickerSymbol as symbol,
                TradeDate as date,
                OpenPrice as open,
                HighPrice as high,
                LowPrice as low,
                ClosePrice as close,
                TurnoverVol as volume,
                TurnoverValue as amount,
                OpenInterest as open_interest,
                PreSettlementPrice as pre_settlement,
                SettlementPrice as settlement,
                ExercisePrice as strike,
                ExpireDate as expiry
            FROM mkt_optd
            WHERE TickerSymbol = '{symbol}'
            AND TradeDate BETWEEN '{start_str}' AND '{end_str}'
            ORDER BY TradeDate
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

    def raw_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行原始 SQL 查询（用于探索性查询或复杂联合查询）

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            查询结果 DataFrame
        """
        return self._execute_query(sql, params)

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM mkt_futd LIMIT 1"))
                count = result.scalar()
                logger.info(f"Tonglian connection test passed. Sample count: {count}")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

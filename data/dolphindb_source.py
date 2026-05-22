"""
DolphinDB时序数据库数据源

DolphinDB是高性能的时序数据库，适合存储高频行情数据
需要安装 dolphindb 包: pip install dolphindb
"""
from datetime import datetime
from typing import List, Optional, Union

import pandas as pd
from loguru import logger

from config import get_settings
from data.base import DataSourceBase


class DolphinDBSource(DataSourceBase):
    """DolphinDB时序数据库数据源

    适用于存储和查询高频行情数据（分钟级、Tick级）
    优势：高性能写入、时间序列聚合、流计算

    Attributes:
        session: DolphinDB会话
        is_connected: 连接状态
    """

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.session = None
        self.is_connected = False
        self._connect()

    def _connect(self):
        """建立DolphinDB连接"""
        try:
            # 尝试导入dolphindb
            import dolphindb as ddb

            config = self.settings.dolphindb

            self.session = ddb.session()
            self.session.connect(config.host, config.port, config.user, config.password)
            self.is_connected = True

            logger.info(f"DolphinDB connected: {config.host}:{config.port}")

        except ImportError:
            logger.warning("dolphindb package not installed. Run: pip install dolphindb")
            self.session = None
        except Exception as e:
            logger.error(f"Failed to connect DolphinDB: {e}")
            self.session = None

    def ensure_connected(self) -> bool:
        """确保连接状态"""
        if not self.is_connected and self.session is None:
            self._connect()
        return self.is_connected

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频数据"""
        if not self.ensure_connected():
            return pd.DataFrame()

        if isinstance(symbol, list):
            symbols = "'" + "','".join(symbol) + "'"
        else:
            symbols = f"'{symbol}'"

        start_str = start_date.strftime("%Y.%m.%d") if start_date else "2000.01.01"
        end_str = end_date.strftime("%Y.%m.%d") if end_date else datetime.now().strftime("%Y.%m.%d")

        # 选择字段
        select_fields = ",".join(fields) if fields else "*"

        script = f"""
        select {select_fields} from loadTable("dfs://daily_data", "prices")
        where symbol in ({symbols})
        and date between {start_str} and {end_str}
        """

        try:
            df = self.session.run(script)
            df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as e:
            logger.error(f"Failed to query daily data: {e}")
            return pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟级数据

        DolphinDB擅长处理高频数据
        """
        if not self.ensure_connected():
            return pd.DataFrame()

        start_str = start_date.strftime("%Y.%m.%d") if start_date else "2000.01.01"
        end_str = end_date.strftime("%Y.%m.%d") if end_date else datetime.now().strftime("%Y.%m.%d")

        # 根据频率选择表
        table_name = "minute_bars" if freq == "1min" else f"bars_{freq}"

        script = f"""
        select * from loadTable("dfs://minute_data", "{table_name}")
        where symbol = '{symbol}'
        and datetime between {start_str}T00:00:00 and {end_str}T23:59:59
        """

        try:
            df = self.session.run(script)
            df['datetime'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"Failed to query minute data: {e}")
            return pd.DataFrame()

    def get_tick_data(
        self,
        symbol: str,
        date: datetime,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> pd.DataFrame:
        """获取Tick级数据

        Args:
            symbol: 标的代码
            date: 日期
            start_time: 开始时间 (HH:MM:SS)
            end_time: 结束时间 (HH:MM:SS)

        Returns:
            Tick数据DataFrame
        """
        if not self.ensure_connected():
            return pd.DataFrame()

        date_str = date.strftime("%Y.%m.%d")

        time_filter = ""
        if start_time:
            time_filter += f" and time >= {start_time}"
        if end_time:
            time_filter += f" and time <= {end_time}"

        script = f"""
        select * from loadTable("dfs://tick_data", "ticks")
        where symbol = '{symbol}'
        and date = {date_str}
        {time_filter}
        """

        try:
            df = self.session.run(script)
            df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
            return df
        except Exception as e:
            logger.error(f"Failed to query tick data: {e}")
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

        # TODO: 实现财务数据查询
        logger.warning("DolphinDB fundamentals not yet implemented")
        return pd.DataFrame()

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股"""
        if not self.ensure_connected():
            return []

        date_str = date.strftime("%Y.%m.%d") if date else datetime.now().strftime("%Y.%m.%d")

        script = f"""
        select symbol from loadTable("dfs://index_data", "components")
        where index_code = '{index_code}'
        and date <= {date_str}
        order by date desc
        limit 1
        """

        try:
            df = self.session.run(script)
            return df['symbol'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Failed to query index components: {e}")
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

        start_str = start_date.strftime("%Y.%m.%d") if start_date else "2000.01.01"
        end_str = end_date.strftime("%Y.%m.%d") if end_date else datetime.now().strftime("%Y.%m.%d")

        script = f"""
        select * from loadTable("dfs://calendar", "trade_dates")
        where market = '{market}'
        and date between {start_str} and {end_str}
        """

        try:
            df = self.session.run(script)
            df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as e:
            logger.error(f"Failed to query calendar: {e}")
            return pd.DataFrame()

    def write_data(
        self,
        df: pd.DataFrame,
        database: str,
        table: str,
        partition_columns: Optional[List[str]] = None
    ) -> bool:
        """写入数据到DolphinDB

        Args:
            df: DataFrame数据
            database: 目标数据库
            table: 目标表
            partition_columns: 分区列

        Returns:
            是否成功
        """
        if not self.ensure_connected():
            return False

        try:
            # 使用session.upload上传数据
            self.session.upload({"tmp_data": df})

            # 创建表（如果不存在）并追加数据
            script = f"""
            t = tmp_data
            if(not existsDatabase("dfs://{database}")){{
                db = database("dfs://{database}", VALUE, 2020.01.01..2030.12.31)
            }}else{{
                db = database("dfs://{database}")
            }}

            if(not existsTable("dfs://{database}", "{table}")){{
                db.createPartitionedTable(t, "{table}", `date)
            }}

            loadTable("dfs://{database}", "{table}").append!(t)
            """

            self.session.run(script)
            logger.info(f"Written {len(df)} rows to {database}.{table}")
            return True

        except Exception as e:
            logger.error(f"Failed to write data: {e}")
            return False

    def aggregate_time_series(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        freq: str = "1d",
        func: str = "last"
    ) -> pd.DataFrame:
        """时间序列聚合

        DolphinDB的强项，高效的时间序列计算

        Args:
            symbol: 标的代码
            start_date: 开始日期
            end_date: 结束日期
            freq: 频率 (1d, 1h, 30m, 5m, 1m)
            func: 聚合函数 (last, first, max, min, avg, sum)

        Returns:
            聚合后的DataFrame
        """
        if not self.ensure_connected():
            return pd.DataFrame()

        start_str = start_date.strftime("%Y.%m.%d")
        end_str = end_date.strftime("%Y.%m.%d")

        script = f"""
        bar(
            select datetime, close, volume from loadTable("dfs://minute_data", "minute_bars")
            where symbol = '{symbol}'
            and datetime between {start_str}T00:00:00 and {end_str}T23:59:59,
            {freq},
            0
        )
        """

        try:
            df = self.session.run(script)
            return df
        except Exception as e:
            logger.error(f"Failed to aggregate: {e}")
            return pd.DataFrame()

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            version = self.session.run("version()")
            logger.info(f"DolphinDB connection test passed. Version: {version}")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def __del__(self):
        """析构时关闭连接"""
        if self.session and self.is_connected:
            try:
                self.session.close()
                logger.info("DolphinDB connection closed")
            except:
                pass

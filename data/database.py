from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional, Union

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import get_settings


class DatabaseManager:
    """数据库管理器

    负责与PostgreSQL数据库的交互，包括行情数据、因子数据的存储和查询
    """

    def __init__(self):
        self.settings = get_settings()
        self.engine = create_engine(
            self.settings.database.url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("DatabaseManager initialized")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库会话（上下文管理器）"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    # ==================== 股票价格表操作 ====================

    def save_stock_prices(self, df: pd.DataFrame) -> bool:
        """保存股票价格数据（前复权）

        Args:
            df: DataFrame with columns [symbol, date, open, high, low, close, volume, amount, adj_factor, ...]
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_stock", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_stock")
            return True
        except Exception as e:
            logger.error(f"Failed to save stock prices: {e}")
            return False

    def get_stock_prices(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """查询股票价格"""
        if isinstance(symbol, str):
            symbol = [symbol]
        symbols_str = ",".join([f"'{s}'" for s in symbol])
        field_str = ",".join(fields) if fields else "*"

        sql = f"SELECT {field_str} FROM prices_stock WHERE symbol IN ({symbols_str})"
        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 期货价格表操作 ====================

    def save_future_prices(self, df: pd.DataFrame) -> bool:
        """保存期货原始合约价格数据"""
        if df.empty:
            return False
        try:
            df.to_sql("prices_future", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_future")
            return True
        except Exception as e:
            logger.error(f"Failed to save future prices: {e}")
            return False

    def get_future_prices(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询期货原始合约价格"""
        if isinstance(symbol, str):
            symbol = [symbol]
        symbols_str = ",".join([f"'{s}'" for s in symbol])

        sql = f"SELECT * FROM prices_future WHERE symbol IN ({symbols_str})"
        params = {}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_future_continuous(self, df: pd.DataFrame) -> bool:
        """保存期货连续合约价格（展期后）

        Args:
            df: DataFrame with columns from calculate_static_roll()
        """
        if df.empty:
            return False
        try:
            df.to_sql("prices_future_continuous", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_future_continuous")
            return True
        except Exception as e:
            logger.error(f"Failed to save continuous prices: {e}")
            return False

    def get_future_continuous(
        self,
        underlying: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        roll_start_days: int = 10,
        roll_end_days: int = 3,
    ) -> pd.DataFrame:
        """查询期货连续合约价格"""
        sql = """
            SELECT * FROM prices_future_continuous
            WHERE underlying = :underlying
            AND roll_start_days = :p AND roll_end_days = :q
        """
        params = {
            "underlying": underlying,
            "p": roll_start_days,
            "q": roll_end_days
        }
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 指数价格表操作 ====================

    def save_index_prices(self, df: pd.DataFrame) -> bool:
        """保存指数价格数据"""
        if df.empty:
            return False
        try:
            df.to_sql("prices_index", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to prices_index")
            return True
        except Exception as e:
            logger.error(f"Failed to save index prices: {e}")
            return False

    def get_index_prices(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询指数价格"""
        sql = "SELECT * FROM prices_index WHERE symbol = :symbol"
        params = {"symbol": symbol}
        if start_date:
            sql += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += " AND date <= :end_date"
            params["end_date"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 统一价格查询接口 ====================

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        asset_class: Optional[str] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """从数据库查询日频行情数据（统一接口）

        根据 asset_class 自动选择对应的表查询
        """
        if isinstance(symbol, str):
            symbol = [symbol]

        results = []
        for sym in symbol:
            # 根据 symbol 判断资产类型
            if asset_class is None:
                if sym.startswith(('IF', 'IC', 'IM', 'IH', 'TF', 'T', 'TS', 'TL')) and len(sym) <= 6:
                    asset_type = 'future_continuous'
                elif '.' in sym:
                    asset_type = 'stock'
                else:
                    asset_type = 'index'
            else:
                asset_type = asset_class

            if asset_type == 'stock':
                df = self.get_stock_prices(sym, start_date, end_date, fields)
            elif asset_type == 'future_continuous':
                underlying = sym if len(sym) <= 4 else sym[:2]
                df = self.get_future_continuous(underlying, start_date, end_date)
            elif asset_type == 'index':
                df = self.get_index_prices(sym, start_date, end_date)
            else:
                # 默认尝试 stock 表
                df = self.get_stock_prices(sym, start_date, end_date, fields)

            if not df.empty:
                df['symbol'] = sym
                results.append(df)

        if not results:
            return pd.DataFrame()

        return pd.concat(results, ignore_index=True)

    def save_daily_price(self, df: pd.DataFrame, asset_class: str = 'stock') -> bool:
        """保存日频行情数据（统一接口）

        Args:
            df: DataFrame with price data
            asset_class: 'stock'/'future'/'future_continuous'/'index'
        """
        if df.empty:
            logger.warning("Empty dataframe, nothing to save")
            return False

        if asset_class == 'stock':
            return self.save_stock_prices(df)
        elif asset_class == 'future':
            return self.save_future_prices(df)
        elif asset_class == 'future_continuous':
            return self.save_future_continuous(df)
        elif asset_class == 'index':
            return self.save_index_prices(df)
        else:
            logger.error(f"Unknown asset_class: {asset_class}")
            return False
            return pd.read_sql(text(sql), conn, params=params)

    def save_factor_data(self, df: pd.DataFrame, factor_name: str) -> bool:
        """保存因子数据

        Args:
            df: DataFrame with columns [symbol, date, factor_value]
            factor_name: 因子名称，用于表名
        """
        if df.empty:
            return False

        table_name = f"factor_{factor_name}"

        try:
            df.to_sql(
                table_name,
                self.engine,
                if_exists="append",
                index=False
            )
            logger.info(f"Saved {len(df)} rows to {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save factor data: {e}")
            return False

    def execute_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """执行原始SQL查询

        Args:
            sql: SQL语句
            params: 查询参数

        Returns:
            查询结果DataFrame
        """
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 策略管理表操作 ====================

    def save_strategy_nav(self, df: pd.DataFrame) -> bool:
        """保存策略净值数据"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_nav", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_nav")
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy NAV: {e}")
            return False

    def get_strategy_nav(
        self,
        strategy_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略净值"""
        sql = "SELECT * FROM strategy_nav WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_target_positions(self, df: pd.DataFrame) -> bool:
        """保存目标持仓（策略信号）"""
        if df.empty:
            return False
        try:
            df.to_sql("target_positions", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to target_positions")
            return True
        except Exception as e:
            logger.error(f"Failed to save target positions: {e}")
            return False

    def get_target_positions(
        self,
        strategy_code: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询目标持仓"""
        sql = "SELECT * FROM target_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_actual_positions(self, df: pd.DataFrame) -> bool:
        """保存实际持仓"""
        if df.empty:
            return False
        try:
            df.to_sql("actual_positions", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to actual_positions")
            return True
        except Exception as e:
            logger.error(f"Failed to save actual positions: {e}")
            return False

    def get_actual_positions(
        self,
        strategy_code: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询实际持仓"""
        sql = "SELECT * FROM actual_positions WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if date:
            sql += " AND date = :date"
            params["date"] = date
        sql += " ORDER BY date DESC, symbol"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_trades(self, df: pd.DataFrame) -> bool:
        """保存交易记录"""
        if df.empty:
            return False
        try:
            df.to_sql("trades", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to trades")
            return True
        except Exception as e:
            logger.error(f"Failed to save trades: {e}")
            return False

    def get_trades(
        self,
        strategy_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询交易记录"""
        sql = "SELECT * FROM trades WHERE strategy_code = :code"
        params = {"code": strategy_code}
        if start_date:
            sql += " AND trade_date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND trade_date <= :end"
            params["end"] = end_date
        sql += " ORDER BY trade_date DESC, trade_time DESC"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 展期执行记录 ====================

    def save_roll_execution(self, df: pd.DataFrame) -> bool:
        """保存期货展期执行记录"""
        if df.empty:
            return False
        try:
            df.to_sql("roll_executions", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to roll_executions")
            return True
        except Exception as e:
            logger.error(f"Failed to save roll executions: {e}")
            return False

    # ==================== 资产和基础数据 ====================

    def save_assets(self, df: pd.DataFrame) -> bool:
        """保存资产信息"""
        if df.empty:
            return False
        try:
            df.to_sql("assets", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to assets")
            return True
        except Exception as e:
            logger.error(f"Failed to save assets: {e}")
            return False

    def get_assets(self, asset_class: Optional[str] = None) -> pd.DataFrame:
        """查询资产列表"""
        sql = "SELECT * FROM assets WHERE is_active = TRUE"
        params = {}
        if asset_class:
            sql += " AND asset_class = :cls"
            params["cls"] = asset_class
        sql += " ORDER BY symbol"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_trade_calendar(self, df: pd.DataFrame) -> bool:
        """保存交易日历"""
        if df.empty:
            return False
        try:
            df.to_sql("trade_calendar", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to trade_calendar")
            return True
        except Exception as e:
            logger.error(f"Failed to save trade calendar: {e}")
            return False

    def get_trade_calendar(
        self,
        market: str = "SSE",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询交易日历"""
        sql = "SELECT * FROM trade_calendar WHERE market = :market"
        params = {"market": market}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    # ==================== 对冲策略专用表操作 ====================

    def save_hedge_instrument_mapping(self, df: pd.DataFrame) -> bool:
        """保存对冲工具映射关系"""
        if df.empty:
            return False
        try:
            df.to_sql("hedge_instrument_mapping", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to hedge_instrument_mapping")
            return True
        except Exception as e:
            logger.error(f"Failed to save hedge mapping: {e}")
            return False

    def get_hedge_instruments(
        self,
        underlying_index: str,
        hedge_type: Optional[str] = None,
        active_only: bool = True,
    ) -> pd.DataFrame:
        """查询标的指数的对冲工具列表

        Args:
            underlying_index: 标的指数，如 "000300.SH"
            hedge_type: 筛选特定对冲类型
            active_only: 只返回可用状态的工具
        """
        sql = "SELECT * FROM hedge_instrument_mapping WHERE underlying_index = :idx"
        params = {"idx": underlying_index}

        if active_only:
            sql += " AND is_active = TRUE"
        if hedge_type:
            sql += " AND hedge_type = :type"
            params["type"] = hedge_type
        sql += " ORDER BY priority, hedge_symbol"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_synthetic_index(self, df: pd.DataFrame) -> bool:
        """保存合成指数序列"""
        if df.empty:
            return False
        try:
            df.to_sql("synthetic_index_series", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to synthetic_index_series")
            return True
        except Exception as e:
            logger.error(f"Failed to save synthetic index: {e}")
            return False

    def get_synthetic_index(
        self,
        underlying_index: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询合成指数序列"""
        sql = "SELECT * FROM synthetic_index_series WHERE underlying_index = :idx"
        params = {"idx": underlying_index}
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def save_strategy_index_series(self, df: pd.DataFrame) -> bool:
        """保存策略指数序列（不同对冲工具下的策略表现）"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_index_series", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_index_series")
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy index: {e}")
            return False

    def get_strategy_index_series(
        self,
        strategy_code: str,
        underlying_index: Optional[str] = None,
        hedge_symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略指数序列

        Returns:
            DataFrame: 包含不同对冲工具下的策略指数点位
        """
        sql = "SELECT * FROM strategy_index_series WHERE strategy_code = :code"
        params = {"code": strategy_code}

        if underlying_index:
            sql += " AND underlying_index = :underlying"
            params["underlying"] = underlying_index
        if hedge_symbol:
            sql += " AND hedge_symbol = :hedge"
            params["hedge"] = hedge_symbol
        if start_date:
            sql += " AND date >= :start"
            params["start"] = start_date
        if end_date:
            sql += " AND date <= :end"
            params["end"] = end_date
        sql += " ORDER BY date, hedge_symbol"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def compare_hedge_instruments(
        self,
        strategy_code: str,
        underlying_index: str,
        date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """比较同一策略不同对冲工具的表现"""
        if date is None:
            date = datetime.now()

        sql = """
        SELECT
            s1.hedge_symbol as hedge_1,
            s1.hedge_type as type_1,
            s1.index_value as value_1,
            s1.cumulative_return as return_1,
            s1.hedge_cost as cost_1,
            s2.hedge_symbol as hedge_2,
            s2.hedge_type as type_2,
            s2.index_value as value_2,
            s2.cumulative_return as return_2,
            s2.hedge_cost as cost_2,
            s1.cumulative_return - s2.cumulative_return as return_diff,
            s1.hedge_cost - s2.hedge_cost as cost_diff
        FROM strategy_index_series s1
        JOIN strategy_index_series s2
            ON s1.strategy_code = s2.strategy_code
            AND s1.underlying_index = s2.underlying_index
            AND s1.date = s2.date
        WHERE s1.strategy_code = :code
        AND s1.underlying_index = :underlying
        AND s1.date = :date
        AND s1.hedge_symbol < s2.hedge_symbol
        ORDER BY ABS(s1.cumulative_return - s2.cumulative_return) DESC
        """

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params={
                "code": strategy_code,
                "underlying": underlying_index,
                "date": date
            })

    def save_strategy_hedge_config(self, df: pd.DataFrame) -> bool:
        """保存策略对冲配置"""
        if df.empty:
            return False
        try:
            df.to_sql("strategy_hedge_config", self.engine, if_exists="append", index=False, method="multi")
            logger.info(f"Saved {len(df)} rows to strategy_hedge_config")
            return True
        except Exception as e:
            logger.error(f"Failed to save hedge config: {e}")
            return False

    def get_strategy_hedge_config(
        self,
        strategy_code: str,
        underlying_index: Optional[str] = None,
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """查询策略对冲配置"""
        if as_of_date is None:
            as_of_date = datetime.now()

        sql = """
        SELECT * FROM strategy_hedge_config
        WHERE strategy_code = :code
        AND effective_date <= :date
        AND (expiry_date IS NULL OR expiry_date > :date)
        AND is_active = TRUE
        """
        params = {"code": strategy_code, "date": as_of_date}

        if underlying_index:
            sql += " AND underlying_index = :underlying"
            params["underlying"] = underlying_index
        sql += " ORDER BY effective_date DESC"

        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def create_tables(self):
        """创建基础表结构（执行schema.sql）"""
        schema_file = Path(__file__).parent.parent / "database" / "schema.sql"
        if not schema_file.exists():
            logger.warning(f"Schema file not found: {schema_file}")
            return

        with open(schema_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        statements = [s.strip() for s in sql_content.split(';') if s.strip()]

        with self.engine.connect() as conn:
            with conn.begin():
                for statement in statements:
                    if not statement or statement.startswith('--'):
                        continue
                    try:
                        conn.execute(text(statement + ';'))
                    except Exception as e:
                        if "already exists" not in str(e) and "duplicate" not in str(e).lower():
                            logger.warning(f"Error: {e}")

        logger.info("Database tables created/verified")

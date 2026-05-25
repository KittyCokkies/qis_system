"""
期货展期收益计算模块

支持境内股指和商品期货的展期收益序列计算，用于:
- CTA策略中的展期收益因子
- 期货多头/空头的展期成本分析
- 跨期套利信号生成
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Tuple, Union

import pandas as pd
import numpy as np
from loguru import logger

from data.tonglian_source import TonglianSource


class RollPriceType(str, Enum):
    """展期结算价格类型"""
    CLOSE = "close"           # 收盘价结算
    SETTLEMENT = "settlement" # 结算价结算
    VWAP = "vwap"             # 成交量加权均价（如有）


class RollSignalType(str, Enum):
    """换仓信号指标类型"""
    OPEN_INTEREST = "open_interest"   # 持仓量最大
    VOLUME = "volume"                 # 成交量最大
    COMBINED = "combined"             # 持仓量+成交量综合
    LIQUIDITY = "liquidity"           # 流动性评分（持仓量*成交量）
    STATIC_CALENDAR = "static_calendar"  # 固定日历换月：到期前固定天数换到下月


@dataclass
class RollConfig:
    """展期配置"""
    price_type: RollPriceType = RollPriceType.CLOSE
    signal_type: RollSignalType = RollSignalType.OPEN_INTEREST
    days_before_expiry: int = 5       # 到期前N天开始考虑换仓
    min_roll_days: int = 3            # 最小展期天数（避免到期日换仓）
    weights: Dict[str, float] = None  # 综合评分权重（如使用COMBINED）

    def __post_init__(self):
        if self.weights is None:
            self.weights = {"open_interest": 0.6, "volume": 0.4}


class FutureRollAnalyzer:
    """期货展期收益分析器

    基于通联数据库，支持:
    - 所有境内股指期货（IF、IC、IM、IH等）
    - 所有境内商品期货（流动性筛选）
    - 自定义展期价格和换仓信号

    Example:
        >>> analyzer = FutureRolloverAnalyzer()
        >>> # 计算单品种展期收益
        >>> df = analyzer.calculate_roll_return("IF", "2024-01-01", "2024-12-31")
        >>> # 批量计算所有股指期货
        >>> all_returns = analyzer.batch_calculate(["IF", "IC", "IM", "IH"])
    """

    # 主要股指期货品种代码（通联格式）
    INDEX_FUTURES = ["IF", "IC", "IM", "IH", "TF", "T", "TS", "TL"]

    # 主要商品期货品种（流动性较好）
    COMMODITY_FUTURES = [
        # 贵金属
        "AU", "AG",
        # 有色
        "CU", "AL", "ZN", "PB", "NI", "SN", "SS", "BC",
        # 黑色
        "RB", "HC", "I", "J", "JM", "ZC", "FG", "SF", "SM",
        # 能源化工
        "SC", "FU", "LU", "BU", "TA", "EG", "PG", "PP", "PE", "L", "MA", "UR", "SA", "PF", "SH",
        # 农产品
        "M", "Y", "P", "OI", "RM", "A", "B", "RS", "SR", "CF", "CY", "JD", "LH", "AP", "CJ", "C", "CS"
    ]

    def __init__(self, source: Optional[TonglianSource] = None):
        """
        Args:
            source: TonglianSource实例，None则自动创建
        """
        self.source = source or TonglianSource()
        self.config = RollConfig()
        logger.info("FutureRolloverAnalyzer initialized")

    def get_future_contracts(
        self,
        underlying: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货合约列表及基本信息

        从通联数据库查询期货合约信息，包括:
        - 合约代码
        - 标的品种
        - 到期日/最后交易日
        - 挂牌日

        Args:
            underlying: 标的品种代码，如 "IF"（沪深300股指）、"AU"（黄金）
            start_date: 查询起始日期
            end_date: 查询结束日期

        Returns:
            DataFrame with columns:
            - symbol: 合约代码（如 IF2401）
            - underlying: 标的品种（如 IF）
            - contract_month: 合约月份（如 202401）
            - list_date: 挂牌日
            - last_trade_date: 最后交易日
            - delist_date: 退市日
        """
        # 通联期货合约信息表查询
        # 表名可能是 fut_contract 或 sec_main 中筛选期货
        sql = f"""
        SELECT
            CONTRACT_SYMBOL as symbol,
            UNDERLYING_SYMBOL as underlying,
            CONTRACT_MONTH as contract_month,
            LIST_DATE as list_date,
            LAST_TRADE_DATE as last_trade_date,
            DELIST_DATE as delist_date,
            MULTIPLIER as multiplier,
            TICK_SIZE as tick_size
        FROM fut_contract
        WHERE UNDERLYING_SYMBOL = '{underlying}'
        ORDER BY CONTRACT_MONTH
        """

        df = self.source.raw_query(sql)

        if df.empty:
            # 尝试从 sec_main 查询
            sql = f"""
            SELECT
                SECURITY_ID as symbol,
                SUBSTRING(SECURITY_ID, 1, LENGTH(SECURITY_ID)-4) as underlying,
                SECURITY_NAME_ABBR as name,
                LIST_DATE as list_date,
                DELIST_DATE as delist_date
            FROM sec_main
            WHERE SECURITY_TYPE = 'F'  -- 期货
            AND SECURITY_ID LIKE '{underlying}%'
            ORDER BY LIST_DATE
            """
            df = self.source.raw_query(sql)

        if not df.empty:
            # 标准化日期格式
            for col in ['list_date', 'last_trade_date', 'delist_date']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')

        return df

    def get_future_daily_with_info(
        self,
        underlying: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期货日行情及合约信息（联合查询）

        这是核心查询方法，将行情数据与合约到期信息关联

        Returns:
            DataFrame with columns:
            - symbol: 合约代码
            - date: 交易日
            - close: 收盘价
            - settle: 结算价
            - open_interest: 持仓量
            - turnover: 成交金额/成交量
            - volume: 成交量
            - last_trade_date: 最后交易日
            - days_to_expiry: 距离到期日天数
        """
        start_str = start_date.strftime('%Y-%m-%d') if start_date else '2020-01-01'
        end_str = end_date.strftime('%Y-%m-%d') if end_date else datetime.now().strftime('%Y-%m-%d')

        # 联合查询：日行情 + 合约信息
        sql = f"""
        SELECT
            d.SECURITY_ID as symbol,
            d.TRADE_DATE as date,
            d.CLOSE_PRICE as close,
            d.SETTLEMENT_PRICE as settle,
            d.OPEN_INTEREST as open_interest,
            d.TURNOVER_VOL as volume,
            d.TURNOVER_VALUE as turnover,
            c.LAST_TRADE_DATE as last_trade_date,
            DATEDIFF(c.LAST_TRADE_DATE, d.TRADE_DATE) as days_to_expiry
        FROM mkt_futd d
        LEFT JOIN fut_contract c ON d.SECURITY_ID = c.CONTRACT_SYMBOL
        WHERE d.SECURITY_ID LIKE '{underlying}%'
        AND d.TRADE_DATE BETWEEN '{start_str}' AND '{end_str}'
        AND c.LAST_TRADE_DATE IS NOT NULL
        ORDER BY d.TRADE_DATE, d.OPEN_INTEREST DESC
        """

        df = self.source.raw_query(sql)

        if df.empty:
            # 尝试不使用 JOIN，先查合约信息再查行情
            logger.warning(f"Joint query failed for {underlying}, trying alternative approach")
            return self._get_future_daily_alternative(underlying, start_date, end_date)

        # 数据类型转换
        df['date'] = pd.to_datetime(df['date'])
        df['last_trade_date'] = pd.to_datetime(df['last_trade_date'])

        return df

    def _get_future_daily_alternative(
        self,
        underlying: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> pd.DataFrame:
        """备用方案：分开查询再合并"""
        # 1. 获取合约信息
        contracts = self.get_future_contracts(underlying, start_date, end_date)
        if contracts.empty:
            logger.error(f"No contract info found for {underlying}")
            return pd.DataFrame()

        # 2. 获取所有合约的行情
        all_data = []
        for symbol in contracts['symbol'].tolist():
            try:
                df = self.source.get_future_daily(symbol, start_date, end_date)
                if not df.empty:
                    # 合并合约信息
                    contract_info = contracts[contracts['symbol'] == symbol].iloc[0]
                    df['last_trade_date'] = contract_info.get('last_trade_date')
                    df['underlying'] = underlying
                    all_data.append(df)
            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['date'] = pd.to_datetime(result['date'])
        result['last_trade_date'] = pd.to_datetime(result['last_trade_date'])

        # 计算距离到期天数
        result['days_to_expiry'] = (result['last_trade_date'] - result['date']).dt.days

        return result

    def identify_main_contract(
        self,
        df: pd.DataFrame,
        signal_type: Optional[RolloverSignalType] = None
    ) -> pd.DataFrame:
        """识别每日主力合约

        基于持仓量、成交量或综合指标确定每日主力合约

        Args:
            df: 行情数据（包含多个合约）
            signal_type: 换仓信号类型，None使用配置默认

        Returns:
            DataFrame with 'is_main' column标记主力合约
        """
        signal_type = signal_type or self.config.signal_type

        # 按日期分组
        result = []
        for date, group in df.groupby('date'):
            if len(group) == 0:
                continue

            # 计算主力合约评分
            if signal_type == RolloverSignalType.OPEN_INTEREST:
                group['score'] = group['open_interest']
            elif signal_type == RolloverSignalType.VOLUME:
                group['score'] = group['volume']
            elif signal_type == RolloverSignalType.LIQUIDITY:
                group['score'] = group['open_interest'] * group['volume']
            elif signal_type == RolloverSignalType.COMBINED:
                weights = self.config.weights
                # 标准化
                oi_norm = group['open_interest'] / group['open_interest'].max() if group['open_interest'].max() > 0 else 0
                vol_norm = group['volume'] / group['volume'].max() if group['volume'].max() > 0 else 0
                group['score'] = (
                    weights.get('open_interest', 0.6) * oi_norm +
                    weights.get('volume', 0.4) * vol_norm
                )
            else:
                group['score'] = group['open_interest']

            # 标记主力合约
            group['is_main'] = False
            if not group['score'].isna().all():
                main_idx = group['score'].idxmax()
                group.loc[main_idx, 'is_main'] = True

            result.append(group)

        return pd.concat(result, ignore_index=True)

    def calculate_roll_return(
        self,
        underlying: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        price_type: Optional[RolloverPriceType] = None,
        signal_type: Optional[RolloverSignalType] = None,
    ) -> pd.DataFrame:
        """计算展期收益序列

        核心方法：计算每日展期收益，支持不同价格类型和换仓信号

        展期收益公式:
        - 多头发散（做空近月、做多远月）：(F_far - F_near) / F_near
        - 空头收敛（做多近月、做空远月）：(F_near - F_far) / F_near

        Args:
            underlying: 标的品种代码，如 "IF"、"AU"
            start_date: 起始日期
            end_date: 结束日期
            price_type: 结算价格类型（close/settlement）
            signal_type: 主力合约识别方式

        Returns:
            DataFrame with columns:
            - date: 日期
            - main_contract: 主力合约代码
            - next_contract: 次主力合约代码
            - main_price: 主力合约价格
            - next_price: 次主力合约价格
            - roll_return: 展期收益（年化）
            - days_to_roll: 距离换仓天数
            - signal: 换仓信号（是否到了换仓时点）
        """
        # 参数处理
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        price_type = price_type or self.config.price_type
        price_col = 'close' if price_type == RolloverPriceType.CLOSE else 'settle'

        # 1. 获取数据
        df = self.get_future_daily_with_info(underlying, start_date, end_date)
        if df.empty:
            logger.error(f"No data found for {underlying}")
            return pd.DataFrame()

        # 2. 识别主力合约
        df = self.identify_main_contract(df, signal_type)

        # 3. 计算展期收益
        results = []
        for date, group in df.groupby('date'):
            if len(group) < 2:
                continue

            # 主力合约
            main_contracts = group[group['is_main']]
            if main_contracts.empty:
                continue
            main = main_contracts.iloc[0]

            # 次主力合约（持仓量第二）
            others = group[~group['is_main']].sort_values('open_interest', ascending=False)
            if others.empty:
                continue
            next_contract = others.iloc[0]

            # 计算展期收益
            main_price = main[price_col]
            next_price = next_contract[price_col]

            if pd.isna(main_price) or pd.isna(next_price) or main_price == 0:
                continue

            # 展期收益 = (远月 - 近月) / 近月
            roll_return = (next_price - main_price) / main_price

            # 年化（假设一年12个月合约）
            days_to_expiry = main['days_to_expiry']
            if days_to_expiry > 0:
                annualized_return = roll_return * (365 / days_to_expiry)
            else:
                annualized_return = roll_return * 12  # 近似年化

            # 换仓信号
            signal = self._check_roll_signal(main, next_contract)

            results.append({
                'date': date,
                'underlying': underlying,
                'main_contract': main['symbol'],
                'next_contract': next_contract['symbol'],
                'main_price': main_price,
                'next_price': next_price,
                'price_diff': next_price - main_price,
                'roll_return': roll_return,
                'annualized_return': annualized_return,
                'days_to_expiry': days_to_expiry,
                'main_open_interest': main['open_interest'],
                'next_open_interest': next_contract['open_interest'],
                'roll_signal': signal,
            })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)
        result_df['date'] = pd.to_datetime(result_df['date'])
        result_df = result_df.sort_values('date').reset_index(drop=True)

        logger.info(f"Calculated {len(result_df)} days of roll returns for {underlying}")
        return result_df

    def _check_roll_signal(
        self,
        main_contract: pd.Series,
        next_contract: pd.Series
    ) -> str:
        """检查是否触发换仓信号

        Returns:
            'roll': 应该换仓
            'watch': 接近换仓时点
            'hold': 继续持有
        """
        days_to_expiry = main_contract['days_to_expiry']

        # 到期前N天必须换仓
        if days_to_expiry <= self.config.min_roll_days:
            return 'roll'

        # 到期前缓冲期开始关注
        if days_to_expiry <= self.config.days_before_expiry:
            # 检查次主力流动性是否更好
            if next_contract['open_interest'] > main_contract['open_interest'] * 0.8:
                return 'roll'
            return 'watch'

        return 'hold'

    def batch_calculate(
        self,
        underlyings: List[str],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        **kwargs
    ) -> Dict[str, pd.DataFrame]:
        """批量计算多个品种的展期收益

        Args:
            underlyings: 品种代码列表，如 ["IF", "IC", "AU"]
            **kwargs: 传递给 calculate_roll_return 的参数

        Returns:
            {underlying: DataFrame} 字典
        """
        results = {}
        for underlying in underlyings:
            try:
                logger.info(f"Calculating roll return for {underlying}...")
                df = self.calculate_roll_return(underlying, start_date, end_date, **kwargs)
                if not df.empty:
                    results[underlying] = df
                else:
                    logger.warning(f"No data for {underlying}")
            except Exception as e:
                logger.error(f"Failed to calculate {underlying}: {e}")

        return results

    def get_all_index_futures_returns(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        """获取所有股指期货的展期收益（合并表）"""
        results = self.batch_calculate(self.INDEX_FUTURES, start_date, end_date)

        if not results:
            return pd.DataFrame()

        # 合并所有品种
        all_data = []
        for underlying, df in results.items():
            df = df.copy()
            df['category'] = 'index_future'
            all_data.append(df)

        return pd.concat(all_data, ignore_index=True)

    def get_commodity_futures_returns(
        self,
        commodities: Optional[List[str]] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        """获取商品期货展期收益

        Args:
            commodities: 品种列表，None则使用默认流动性好的品种
        """
        commodities = commodities or self.COMMODITY_FUTURES
        results = self.batch_calculate(commodities, start_date, end_date)

        if not results:
            return pd.DataFrame()

        all_data = []
        for underlying, df in results.items():
            df = df.copy()
            df['category'] = 'commodity_future'
            all_data.append(df)

        return pd.concat(all_data, ignore_index=True)

    def calculate_static_roll(
        self,
        underlying: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        roll_start_days: int = 10,
        roll_end_days: int = 3,
        price_type: RolloverPriceType = RolloverPriceType.CLOSE,
    ) -> pd.DataFrame:
        """固定日历换月策略（连续合约构建）

        支持双窗口控制的展期策略：
        1. roll_start_days (p): 到期前p日开始考虑换仓（避免过早换仓）
        2. roll_end_days (q): 到期前q日必须换仓（避免过晚换仓）
        3. p > q，中间为观察窗口

        换仓规则：
        - 到期日 > p: 持有当月合约（不换仓）
        - q < 到期日 <= p: 观察窗口，可择机换仓（此版本固定换仓）
        - 到期日 <= q: 强制换仓到下月合约

        例如 p=10, q=3：
        - IF2401到期前10天：继续持有IF2401
        - IF2401到期前10天到3天之间：开始观察，准备换仓
        - IF2401到期前3天：强制换成IF2402

        Args:
            underlying: 标的品种代码，如 "IF"、"AU"
            start_date: 起始日期
            end_date: 结束日期
            roll_start_days: 开始观察窗口p（到期前p日开始考虑换仓）
            roll_end_days: 强制换仓窗口q（到期前q日必须换仓）
            price_type: 结算价格类型（close/settlement）

        Returns:
            DataFrame with continuous contract price
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        price_col = 'close' if price_type == RolloverPriceType.CLOSE else 'settle'

        # 1. 获取所有合约信息
        contracts = self.get_future_contracts(underlying, start_date, end_date)
        if contracts.empty:
            logger.error(f"No contract info found for {underlying}")
            return pd.DataFrame()

        if 'last_trade_date' not in contracts.columns:
            logger.error(f"Contract info missing last_trade_date for {underlying}")
            return pd.DataFrame()

        contracts = contracts.sort_values('last_trade_date').reset_index(drop=True)

        # 2. 获取所有合约行情
        all_price_data = []
        for _, contract in contracts.iterrows():
            symbol = contract['symbol']
            try:
                df = self.source.get_future_daily(symbol, start_date, end_date)
                if not df.empty:
                    df['last_trade_date'] = contract['last_trade_date']
                    df['days_to_expiry'] = (df['last_trade_date'] - df['date']).dt.days
                    all_price_data.append(df)
            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")

        if not all_price_data:
            return pd.DataFrame()

        price_df = pd.concat(all_price_data, ignore_index=True)
        price_df = price_df.sort_values(['date', 'last_trade_date']).reset_index(drop=True)

        # 3. 构建连续合约序列
        results = []

        for date, day_group in price_df.groupby('date'):
            tradable = day_group[day_group['days_to_expiry'] >= 0].copy()
            if tradable.empty:
                continue

            tradable = tradable.sort_values('last_trade_date')

            # 双窗口控制的展期逻辑
            # 获取最近到期合约（当月合约）
            if len(tradable) == 0:
                continue

            first_contract = tradable.iloc[0]  # 最近到期的合约
            days_to_first = first_contract['days_to_expiry']

            # 判断当前应持有哪个合约
            if days_to_first > roll_start_days:
                # 到期日 > p: 继续持有当月合约（不换仓期）
                current_row = first_contract
                is_roll = False
                roll_type = 'hold'
            elif roll_end_days < days_to_first <= roll_start_days:
                # q < 到期日 <= p: 观察窗口期
                # 此版本固定换仓：进入观察窗口即换仓
                # 可扩展为：根据流动性指标判断是否换仓
                current_candidates = tradable[tradable['days_to_expiry'] > roll_end_days]
                if len(current_candidates) > 1:
                    # 换到次月合约
                    current_row = current_candidates.iloc[1]
                    is_roll = True
                    roll_type = 'observation_roll'
                else:
                    current_row = first_contract
                    is_roll = False
                    roll_type = 'hold'
            else:
                # 到期日 <= q: 强制换仓期
                if len(tradable) > 1:
                    # 强制换到下月合约
                    current_row = tradable.iloc[1]
                    is_roll = True
                    roll_type = 'forced_roll'
                else:
                    # 没有下月合约，只能继续持有
                    current_row = first_contract
                    is_roll = False
                    roll_type = 'hold_last'

            # 查找下月合约（用于计算展期收益）
            next_candidates = tradable[tradable['last_trade_date'] > current_row['last_trade_date']]
            if len(next_candidates) > 0:
                next_row = next_candidates.iloc[0]
            else:
                next_row = None

            current_price = current_row[price_col]
            next_price = next_row[price_col] if next_row is not None else np.nan

            if not pd.isna(next_price) and current_price != 0:
                price_diff = next_price - current_price
                roll_return = price_diff / current_price
            else:
                price_diff = np.nan
                roll_return = np.nan

            results.append({
                'date': date,
                'underlying': underlying,
                'current_contract': current_row['symbol'],
                'next_contract': next_row['symbol'] if next_row is not None else None,
                'current_price': current_price,
                'next_price': next_price,
                'price_diff': price_diff,
                'roll_return': roll_return,
                'days_to_expiry': current_row['days_to_expiry'],
                'is_roll_day': is_roll,
                'roll_type': roll_type,
                'volume': current_row.get('volume'),
                'open_interest': current_row.get('open_interest'),
            })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)
        result_df['date'] = pd.to_datetime(result_df['date'])
        result_df = result_df.sort_values('date').reset_index(drop=True)

        # 调整连续价格（消除换月跳空）
        result_df = self._adjust_continuous_price(result_df)

        return result_df

    def _adjust_continuous_price(self, df: pd.DataFrame) -> pd.DataFrame:
        """调整连续合约价格，消除换月跳空（向后调整法）"""
        if df.empty:
            return df

        df = df.copy()
        df['continuous_price'] = df['current_price'].copy()

        cumulative_factor = 1.0
        for i in range(len(df) - 1, -1, -1):
            if i < len(df) - 1 and df.iloc[i + 1]['is_roll_day']:
                roll_return = df.iloc[i + 1]['roll_return']
                if not pd.isna(roll_return):
                    cumulative_factor *= (1 + roll_return)
            df.loc[df.index[i], 'continuous_price'] = df.iloc[i]['current_price'] * cumulative_factor

        return df


class RolloverStrategyAdapter:
    """展期收益策略适配器

    为CTA策略提供标准化的展期收益数据接口
    """

    def __init__(self, analyzer: Optional[FutureRolloverAnalyzer] = None):
        self.analyzer = analyzer or FutureRolloverAnalyzer()

    def get_roll_yield_factor(
        self,
        underlyings: List[str],
        lookback_days: int = 20,
        **kwargs
    ) -> pd.DataFrame:
        """获取展期收益因子（用于截面策略）

        计算每个品种的展期收益因子值，可用于:
        - 做多展期收益高的品种（contango时做空近月）
        - 做空展期收益低的品种（backwardation时做多近月）

        Returns:
            DataFrame with columns:
            - underlying: 品种
            - roll_yield: 当前展期收益
            - roll_yield_ma: 展期收益移动平均
            - roll_yield_zscore: 展期收益Z分数
            - rank: 截面排名
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days * 2)

        results = []
        for underlying in underlyings:
            try:
                df = self.analyzer.calculate_roll_return(
                    underlying, start_date, end_date, **kwargs
                )
                if df.empty:
                    continue

                latest = df.iloc[-1].copy()
                latest['roll_yield_ma'] = df['roll_return'].rolling(lookback_days).mean().iloc[-1]
                latest['roll_yield_std'] = df['roll_return'].rolling(lookback_days).std().iloc[-1]
                latest['roll_yield_zscore'] = (
                    (latest['roll_return'] - latest['roll_yield_ma']) / latest['roll_yield_std']
                    if latest['roll_yield_std'] != 0 else 0
                )
                results.append(latest)
            except Exception as e:
                logger.warning(f"Failed to calculate factor for {underlying}: {e}")

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)
        result_df['rank'] = result_df['roll_return'].rank(ascending=False)

        return result_df[['underlying', 'roll_return', 'roll_yield_ma',
                         'roll_yield_zscore', 'rank', 'main_contract', 'next_contract']]

    def get_term_structure(
        self,
        underlying: str,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取期限结构（所有可交易合约的价格曲线）

        用于分析contango/backwardation程度
        """
        if date is None:
            date = datetime.now()

        # 获取该品种所有合约的当日数据
        df = self.analyzer.get_future_daily_with_info(
            underlying,
            date - timedelta(days=30),
            date
        )

        if df.empty:
            return pd.DataFrame()

        # 取最新一天的数据
        latest_date = df['date'].max()
        latest = df[df['date'] == latest_date].copy()

        # 按到期日排序
        latest = latest.sort_values('days_to_expiry')
        latest['term'] = latest['days_to_expiry'].apply(
            lambda x: f"{x}D" if x < 30 else f"{x//30}M"
        )

        return latest[['symbol', 'term', 'days_to_expiry', 'close', 'settle',
                      'open_interest', 'volume']].reset_index(drop=True)

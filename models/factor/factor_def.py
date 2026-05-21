from enum import Enum
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd


class FactorType(Enum):
    """因子类型"""
    VALUE = "value"           # 价值因子
    GROWTH = "growth"         # 成长因子
    QUALITY = "quality"       # 质量因子
    MOMENTUM = "momentum"     # 动量因子
    VOLATILITY = "volatility" # 波动率因子
    LIQUIDITY = "liquidity"   # 流动性因子


class FactorDefinitions:
    """因子定义类

    定义常用的股票因子计算方式
    """

    @staticmethod
    def pe_ratio(close: pd.Series, earnings: pd.Series) -> pd.Series:
        """市盈率 = 股价 / 每股收益"""
        return close / earnings.replace(0, np.nan)

    @staticmethod
    def pb_ratio(close: pd.Series, book_value: pd.Series) -> pd.Series:
        """市净率 = 股价 / 每股净资产"""
        return close / book_value.replace(0, np.nan)

    @staticmethod
    def ps_ratio(close: pd.Series, revenue: pd.Series) -> pd.Series:
        """市销率 = 股价 / 每股营收"""
        return close / revenue.replace(0, np.nan)

    @staticmethod
    def div_yield(dividends: pd.Series, close: pd.Series) -> pd.Series:
        """股息率 = 每股分红 / 股价"""
        return dividends / close.replace(0, np.nan)

    @staticmethod
    def roe(net_income: pd.Series, equity: pd.Series) -> pd.Series:
        """净资产收益率 = 净利润 / 净资产"""
        return net_income / equity.replace(0, np.nan)

    @staticmethod
    def roa(net_income: pd.Series, total_assets: pd.Series) -> pd.Series:
        """总资产收益率 = 净利润 / 总资产"""
        return net_income / total_assets.replace(0, np.nan)

    @staticmethod
    def gross_margin(gross_profit: pd.Series, revenue: pd.Series) -> pd.Series:
        """毛利率 = 毛利 / 营收"""
        return gross_profit / revenue.replace(0, np.nan)

    @staticmethod
    def net_margin(net_income: pd.Series, revenue: pd.Series) -> pd.Series:
        """净利率 = 净利润 / 营收"""
        return net_income / revenue.replace(0, np.nan)

    @staticmethod
    def debt_to_equity(debt: pd.Series, equity: pd.Series) -> pd.Series:
        """资产负债率 = 总负债 / 净资产"""
        return debt / equity.replace(0, np.nan)

    @staticmethod
    def momentum(prices: pd.DataFrame, window: int = 20) -> pd.Series:
        """动量因子 = N日收益率"""
        return prices.pct_change(window)

    @staticmethod
    def rsi(prices: pd.Series, window: int = 14) -> pd.Series:
        """RSI相对强弱指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def volatility(returns: pd.Series, window: int = 20) -> pd.Series:
        """波动率 = N日收益率标准差"""
        return returns.rolling(window=window).std() * np.sqrt(252)

    @staticmethod
    def max_drawdown(prices: pd.Series, window: int = 252) -> pd.Series:
        """最大回撤"""
        rolling_max = prices.rolling(window=window, min_periods=1).max()
        drawdown = (prices - rolling_max) / rolling_max
        return drawdown.rolling(window=window, min_periods=1).min()

    @staticmethod
    def turnover(volume: pd.Series, shares_outstanding: pd.Series) -> pd.Series:
        """换手率 = 成交量 / 流通股本"""
        return volume / shares_outstanding.replace(0, np.nan)

    @staticmethod
    def amihud_illiquidity(returns: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
        """Amihud非流动性指标 = |收益率| / 成交额"""
        return (returns.abs() / volume.replace(0, np.nan)).rolling(window=window).mean()

    @classmethod
    def get_factor_list(cls) -> Dict[str, Dict]:
        """获取所有可用因子列表"""
        return {
            # 价值因子
            "pe_ratio": {"name": "市盈率", "type": FactorType.VALUE, "direction": -1},
            "pb_ratio": {"name": "市净率", "type": FactorType.VALUE, "direction": -1},
            "ps_ratio": {"name": "市销率", "type": FactorType.VALUE, "direction": -1},
            "div_yield": {"name": "股息率", "type": FactorType.VALUE, "direction": 1},

            # 质量因子
            "roe": {"name": "ROE", "type": FactorType.QUALITY, "direction": 1},
            "roa": {"name": "ROA", "type": FactorType.QUALITY, "direction": 1},
            "gross_margin": {"name": "毛利率", "type": FactorType.QUALITY, "direction": 1},
            "net_margin": {"name": "净利率", "type": FactorType.QUALITY, "direction": 1},
            "debt_to_equity": {"name": "资产负债率", "type": FactorType.QUALITY, "direction": -1},

            # 动量因子
            "momentum_20d": {"name": "20日动量", "type": FactorType.MOMENTUM, "direction": 1},
            "momentum_60d": {"name": "60日动量", "type": FactorType.MOMENTUM, "direction": 1},
            "rsi_14d": {"name": "RSI14", "type": FactorType.MOMENTUM, "direction": -1},

            # 波动率因子
            "volatility_20d": {"name": "20日波动率", "type": FactorType.VOLATILITY, "direction": -1},
            "max_drawdown": {"name": "最大回撤", "type": FactorType.VOLATILITY, "direction": -1},

            # 流动性因子
            "turnover": {"name": "换手率", "type": FactorType.LIQUIDITY, "direction": -1},
            "amihud": {"name": "Amihud非流动性", "type": FactorType.LIQUIDITY, "direction": -1},
        }

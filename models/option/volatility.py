from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from loguru import logger

from models.option.pricing import BlackScholesModel, OptionContract


class VolatilityCalculator:
    """波动率计算器"""

    @staticmethod
    def historical_volatility(
        prices: pd.Series,
        window: int = 20,
        annualize: bool = True
    ) -> float:
        """计算历史波动率

        Args:
            prices: 价格序列
            window: 计算窗口
            annualize: 是否年化

        Returns:
            波动率
        """
        if len(prices) < window:
            return np.nan

        log_returns = np.log(prices / prices.shift(1)).dropna()
        vol = log_returns.tail(window).std()

        if annualize:
            vol = vol * np.sqrt(252)

        return vol

    @staticmethod
    def realized_volatility(returns: pd.Series, annualize: bool = True) -> float:
        """计算已实现波动率"""
        vol = returns.std()
        if annualize:
            vol = vol * np.sqrt(252)
        return vol

    @staticmethod
    def parkinson_volatility(
        high: pd.Series,
        low: pd.Series,
        window: int = 20
    ) -> float:
        """Parkinson波动率（基于日内高低价）"""
        log_hl = np.log(high / low)
        var = (log_hl ** 2).rolling(window).mean() / (4 * np.log(2))
        return np.sqrt(var.mean() * 252)

    @staticmethod
    def garman_klass_volatility(
        open_p: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 20
    ) -> float:
        """Garman-Klass波动率（更高效的估计量）"""
        log_hl = np.log(high / low) ** 2
        log_co = np.log(close / open_p) ** 2

        var = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
        return np.sqrt(var.rolling(window).mean().mean() * 252)

    @staticmethod
    def ewma_volatility(
        returns: pd.Series,
        lambda_param: float = 0.94,
        initial_vol: Optional[float] = None
    ) -> pd.Series:
        """EWMA波动率（RiskMetrics方法）"""
        var_series = pd.Series(index=returns.index, dtype=float)

        if initial_vol is None:
            var = returns.var()
        else:
            var = initial_vol ** 2

        for i, ret in enumerate(returns):
            if i == 0:
                var_series.iloc[i] = var
            else:
                var = lambda_param * var + (1 - lambda_param) * ret ** 2
                var_series.iloc[i] = var

        return np.sqrt(var_series * 252)


class VolatilitySurface:
    """波动率曲面

    管理不同行权价和到期日的隐含波动率数据
    """

    def __init__(self, underlying: str, as_of: datetime):
        self.underlying = underlying
        self.as_of = as_of
        self.data: pd.DataFrame = pd.DataFrame()

    def add_point(
        self,
        strike: float,
        expiry: datetime,
        option_type: str,
        implied_vol: float,
        delta: Optional[float] = None
    ):
        """添加波动率数据点"""
        new_row = pd.DataFrame({
            "strike": [strike],
            "expiry": [expiry],
            "option_type": [option_type],
            "implied_vol": [implied_vol],
            "delta": [delta],
            "time_to_maturity": [(expiry - self.as_of).days / 365]
        })
        self.data = pd.concat([self.data, new_row], ignore_index=True)

    def get_vol(
        self,
        strike: float,
        time_to_maturity: float,
        method: str = "linear"
    ) -> Optional[float]:
        """从曲面获取波动率（插值）"""
        if self.data.empty:
            return None

        # 简化处理：先在行权价维度插值
        atm_data = self.data[
            np.abs(self.data["time_to_maturity"] - time_to_maturity) < 0.05
        ]

        if atm_data.empty:
            return None

        strikes = atm_data["strike"].values
        vols = atm_data["implied_vol"].values

        if len(strikes) < 2:
            return vols[0] if len(vols) > 0 else None

        # 线性插值
        if method == "linear":
            interp = interp1d(strikes, vols, bounds_error=False, fill_value="extrapolate")
            return float(interp(strike))

        return None

    def skew(self, time_to_maturity: float) -> pd.Series:
        """获取波动率偏斜（某一到期日）"""
        mask = np.abs(self.data["time_to_maturity"] - time_to_maturity) < 0.05
        return self.data[mask].set_index("strike")["implied_vol"]

    def term_structure(self, delta: float = 0.5) -> pd.Series:
        """获取波动率期限结构（某一delta）"""
        mask = np.abs(self.data["delta"] - delta) < 0.1
        return self.data[mask].set_index("time_to_maturity")["implied_vol"]

    def to_dataframe(self) -> pd.DataFrame:
        """导出DataFrame"""
        return self.data.copy()


class VolatilityCarryCalculator:
    """波动率套利计算器

    用于计算不同期限/行权价之间的波动率差异
    """

    def __init__(self, rate: float = 0.03):
        self.rate = rate

    def calendar_spread_analysis(
        self,
        front_contract: OptionContract,
        back_contract: OptionContract,
        spot: float,
        front_vol: float,
        back_vol: float
    ) -> Dict:
        """日历价差分析

        分析卖出近月、买入远月的波动率套利机会
        """
        # 计算两个合约的希腊值
        from models.option.greeks import GreeksCalculator

        calc = GreeksCalculator(self.rate)
        front_greeks = calc.calculate(front_contract, spot, front_vol)
        back_greeks = calc.calculate(back_contract, spot, back_vol)

        # 计算vega加权比例
        if front_greeks.vega != 0:
            hedge_ratio = back_greeks.vega / front_greeks.vega
        else:
            hedge_ratio = 1

        # 计算theta收益 vs vega风险
        theta_capture = -front_greeks.theta  # 卖出近月的theta收入
        theta_cost = -back_greeks.theta * hedge_ratio  # 买入远月的theta成本
        net_theta = theta_capture - theta_cost

        return {
            "front_vol": front_vol,
            "back_vol": back_vol,
            "vol_spread": back_vol - front_vol,
            "hedge_ratio": hedge_ratio,
            "front_theta": front_greeks.theta,
            "back_theta": back_greeks.theta,
            "net_theta_daily": net_theta,
            "vega_risk": front_greeks.vega,
            "days_to_front_expiry": front_contract.time_to_maturity() * 365,
        }

    def vol_cone_analysis(
        self,
        returns: pd.Series,
        windows: List[int] = [20, 60, 120, 252]
    ) -> pd.DataFrame:
        """波动率锥分析

        用于判断当前波动率在历史分布中的位置
        """
        results = []

        for window in windows:
            rolling_vols = returns.rolling(window).std() * np.sqrt(252)
            results.append({
                "window": window,
                "current": rolling_vols.iloc[-1],
                "min": rolling_vols.min(),
                "max": rolling_vols.max(),
                "median": rolling_vols.median(),
                "percentile_25": rolling_vols.quantile(0.25),
                "percentile_75": rolling_vols.quantile(0.75),
            })

        return pd.DataFrame(results)

    def expected_volatility_premium(
        self,
        implied_vol: float,
        realized_vol_history: pd.Series,
        lookback_days: int = 252
    ) -> Dict:
        """计算预期波动率溢价

        历史来看，隐含波动率通常高于实际波动率（波动率风险溢价）
        """
        hist_realized = realized_vol_history.tail(lookback_days)

        avg_realized = hist_realized.mean()
        vol_premium = implied_vol - avg_realized

        # 计算历史溢价分布
        # 假设当前IV是过去一段时间的均值，计算RV的分布
        premium_percentile = (hist_realized > implied_vol).mean()

        return {
            "implied_vol": implied_vol,
            "avg_realized_vol": avg_realized,
            "vol_premium": vol_premium,
            "premium_percentile": premium_percentile,
            "trade_signal": "sell_vol" if vol_premium > 0.05 else "buy_vol" if vol_premium < -0.02 else "neutral"
        }

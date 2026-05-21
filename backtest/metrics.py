from typing import Optional

import numpy as np
import pandas as pd


class PerformanceMetrics:
    """绩效指标计算"""

    def __init__(self, returns: pd.Series, risk_free_rate: float = 0.02):
        self.returns = returns
        self.risk_free_rate = risk_free_rate

    def total_return(self) -> float:
        """总收益率"""
        return (1 + self.returns).prod() - 1

    def annual_return(self) -> float:
        """年化收益率"""
        n_years = len(self.returns) / 252  # 假设日收益率
        return (1 + self.total_return()) ** (1 / n_years) - 1

    def volatility(self) -> float:
        """年化波动率"""
        return self.returns.std() * np.sqrt(252)

    def sharpe_ratio(self) -> float:
        """夏普比率"""
        excess_return = self.returns.mean() * 252 - self.risk_free_rate
        vol = self.returns.std() * np.sqrt(252)
        if vol == 0:
            return 0
        return excess_return / vol

    def sortino_ratio(self) -> float:
        """索提诺比率"""
        excess_return = self.returns.mean() * 252 - self.risk_free_rate
        downside_std = self.returns[self.returns < 0].std() * np.sqrt(252)
        if downside_std == 0:
            return 0
        return excess_return / downside_std

    def max_drawdown(self) -> float:
        """最大回撤"""
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

    def calmar_ratio(self) -> float:
        """卡玛比率"""
        annual_ret = self.annual_return()
        max_dd = abs(self.max_drawdown())
        if max_dd == 0:
            return 0
        return annual_ret / max_dd

    def win_rate(self) -> float:
        """胜率"""
        if len(self.returns) == 0:
            return 0
        return (self.returns > 0).sum() / len(self.returns)

    def profit_factor(self) -> float:
        """盈亏比"""
        gains = self.returns[self.returns > 0].sum()
        losses = abs(self.returns[self.returns < 0].sum())
        if losses == 0:
            return float('inf') if gains > 0 else 0
        return gains / losses

    def var(self, confidence: float = 0.05) -> float:
        """Value at Risk"""
        return self.returns.quantile(confidence)

    def cvar(self, confidence: float = 0.05) -> float:
        """Conditional Value at Risk (Expected Shortfall)"""
        var = self.var(confidence)
        return self.returns[self.returns <= var].mean()

    def information_ratio(self, benchmark_returns: pd.Series) -> float:
        """信息比率"""
        active_return = self.returns - benchmark_returns
        tracking_error = active_return.std() * np.sqrt(252)
        if tracking_error == 0:
            return 0
        return active_return.mean() * 252 / tracking_error

    def beta(self, benchmark_returns: pd.Series) -> float:
        """Beta系数"""
        covariance = self.returns.cov(benchmark_returns)
        benchmark_variance = benchmark_returns.var()
        if benchmark_variance == 0:
            return 0
        return covariance / benchmark_variance

    def alpha(self, benchmark_returns: pd.Series) -> float:
        """Alpha (年化)"""
        beta = self.beta(benchmark_returns)
        return (self.returns.mean() * 252 -
                self.risk_free_rate -
                beta * (benchmark_returns.mean() * 252 - self.risk_free_rate))

    def get_summary(self) -> pd.Series:
        """获取所有指标摘要"""
        return pd.Series({
            "Total Return": f"{self.total_return():.2%}",
            "Annual Return": f"{self.annual_return():.2%}",
            "Volatility": f"{self.volatility():.2%}",
            "Sharpe Ratio": f"{self.sharpe_ratio():.2f}",
            "Sortino Ratio": f"{self.sortino_ratio():.2f}",
            "Max Drawdown": f"{self.max_drawdown():.2%}",
            "Calmar Ratio": f"{self.calmar_ratio():.2f}",
            "Win Rate": f"{self.win_rate():.2%}",
            "Profit Factor": f"{self.profit_factor():.2f}",
            "VaR (5%)": f"{self.var():.2%}",
            "CVaR (5%)": f"{self.cvar():.2%}",
        })

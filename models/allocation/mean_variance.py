from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from scipy.optimize import minimize

from models.base import AllocationModelBase


class MeanVarianceModel(AllocationModelBase):
    """均值-方差优化模型

    马科维茨均值-方差优化，可以优化夏普比率、最小方差、目标收益等

    Attributes:
        assets: 资产列表
        objective: 优化目标 ("sharpe", "min_variance", "target_return")
        target_return: 目标收益率（仅在target_return模式下使用）
        risk_free_rate: 无风险利率
        max_weight: 单资产最大权重
        min_weight: 单资产最小权重
    """

    def __init__(
        self,
        assets: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "objective": "sharpe",  # sharpe, min_variance, max_return, target_return
            "target_return": 0.1,   # 年化目标收益
            "risk_free_rate": 0.02, # 年化无风险利率
            "max_weight": 0.5,
            "min_weight": 0.0,
            "allow_short": False
        }
        if params:
            default_params.update(params)

        super().__init__("MeanVariance", assets, default_params)
        self.n_assets = len(assets)
        self.expected_returns: Optional[np.ndarray] = None

    def fit(self, data: pd.DataFrame) -> "MeanVarianceModel":
        """计算期望收益和协方差矩阵

        Args:
            data: 资产收益率DataFrame
        """
        if isinstance(data, pd.DataFrame):
            returns = data[self.assets] if all(a in data.columns for a in self.assets) else data
        else:
            raise ValueError("Data must be a DataFrame")

        # 计算年化期望收益（假设输入是日收益率）
        self.expected_returns = returns.mean().values * 252
        self.cov_matrix = returns.cov().values * 252  # 年化协方差
        self.is_fitted = True

        logger.info(f"MeanVariance model fitted: expected returns range "
                   f"[{self.expected_returns.min():.2%}, {self.expected_returns.max():.2%}]")
        return self

    def _portfolio_performance(self, weights: np.ndarray) -> tuple:
        """计算组合绩效

        Returns:
            (收益, 波动率, 夏普比率)
        """
        port_return = np.sum(self.expected_returns * weights)
        port_volatility = np.sqrt(weights @ self.cov_matrix @ weights)
        sharpe = (port_return - self.params["risk_free_rate"]) / port_volatility
        return port_return, port_volatility, sharpe

    def _neg_sharpe_ratio(self, weights: np.ndarray) -> float:
        """负夏普比率（用于最小化）"""
        return -self._portfolio_performance(weights)[2]

    def _portfolio_variance(self, weights: np.ndarray) -> float:
        """组合方差"""
        return weights @ self.cov_matrix @ weights

    def _neg_portfolio_return(self, weights: np.ndarray) -> float:
        """负组合收益（用于最大化收益）"""
        return -np.sum(self.expected_returns * weights)

    def optimize(self, returns: pd.DataFrame) -> np.ndarray:
        """执行优化

        Args:
            returns: 资产收益率DataFrame

        Returns:
            最优权重
        """
        if not self.is_fitted:
            self.fit(returns)

        objective = self.params["objective"]
        bounds = [
            (self.params["min_weight"], self.params["max_weight"])
            for _ in range(self.n_assets)
        ]

        # 权重和为1的约束
        constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

        # 目标收益约束（如果适用）
        if objective == "target_return":
            target = self.params["target_return"]
            constraints.append({
                "type": "eq",
                "fun": lambda x: np.sum(self.expected_returns * x) - target
            })

        initial_guess = np.ones(self.n_assets) / self.n_assets

        # 选择优化目标
        if objective == "sharpe":
            obj_func = self._neg_sharpe_ratio
        elif objective == "min_variance":
            obj_func = self._portfolio_variance
        elif objective == "max_return":
            obj_func = self._neg_portfolio_return
        elif objective == "target_return":
            obj_func = self._portfolio_variance
        else:
            raise ValueError(f"Unknown objective: {objective}")

        result = minimize(
            obj_func,
            initial_guess,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints
        )

        if result.success:
            self.weights = result.x
            port_ret, port_vol, sharpe = self._portfolio_performance(self.weights)
            logger.info(f"Optimization successful: return={port_ret:.2%}, "
                       f"volatility={port_vol:.2%}, sharpe={sharpe:.2f}")
        else:
            logger.warning(f"Optimization failed: {result.message}")
            self.weights = initial_guess

        return self.weights

    def get_efficient_frontier(self, n_points: int = 50) -> pd.DataFrame:
        """计算有效前沿

        Args:
            n_points: 计算的点数

        Returns:
            有效前沿DataFrame (return, volatility, sharpe)
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")

        target_returns = np.linspace(
            self.expected_returns.min(),
            self.expected_returns.max(),
            n_points
        )

        efficient_portfolios = []
        bounds = [
            (self.params["min_weight"], self.params["max_weight"])
            for _ in range(self.n_assets)
        ]

        for target in target_returns:
            constraints = [
                {"type": "eq", "fun": lambda x: np.sum(x) - 1.0},
                {"type": "eq", "fun": lambda x: np.sum(self.expected_returns * x) - target}
            ]

            result = minimize(
                self._portfolio_variance,
                np.ones(self.n_assets) / self.n_assets,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints
            )

            if result.success:
                weights = result.x
                ret, vol, sharpe = self._portfolio_performance(weights)
                efficient_portfolios.append({
                    "return": ret,
                    "volatility": vol,
                    "sharpe": sharpe,
                    "weights": weights
                })

        return pd.DataFrame(efficient_portfolios)

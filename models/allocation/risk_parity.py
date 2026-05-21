from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from scipy.optimize import minimize

from models.base import AllocationModelBase


class RiskParityModel(AllocationModelBase):
    """风险平价模型

    使各资产对组合总风险的贡献相等，实现风险分散

    Attributes:
        assets: 资产列表
        risk_target: 风险目标（可选）
        max_weight: 单资产最大权重
        min_weight: 单资产最小权重
    """

    def __init__(
        self,
        assets: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "max_weight": 0.5,
            "min_weight": 0.0,
            "risk_target": None,
            "method": "inverse_variance"  # or "equal_risk_contribution"
        }
        if params:
            default_params.update(params)

        super().__init__("RiskParity", assets, default_params)
        self.n_assets = len(assets)

    def _calculate_risk_contribution(self, weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
        """计算各资产的风险贡献

        Args:
            weights: 权重数组
            cov_matrix: 协方差矩阵

        Returns:
            各资产的风险贡献
        """
        port_vol = np.sqrt(weights @ cov_matrix @ weights)
        marginal_risk = cov_matrix @ weights
        risk_contrib = weights * marginal_risk / port_vol
        return risk_contrib

    def _risk_parity_objective(self, weights: np.ndarray, cov_matrix: np.ndarray) -> float:
        """风险平价目标函数（最小化方差）"""
        risk_contrib = self._calculate_risk_contribution(weights, cov_matrix)
        target_risk = np.mean(risk_contrib)
        return np.sum((risk_contrib - target_risk) ** 2)

    def _inverse_variance_weights(self, cov_matrix: np.ndarray) -> np.ndarray:
        """逆方差权重（简化版风险平价）"""
        inv_var = 1.0 / np.diag(cov_matrix)
        weights = inv_var / inv_var.sum()
        return weights

    def fit(self, data: pd.DataFrame) -> "RiskParityModel":
        """计算协方差矩阵

        Args:
            data: 资产收益率DataFrame，columns为资产代码
        """
        if isinstance(data, pd.DataFrame):
            returns = data[self.assets] if all(a in data.columns for a in self.assets) else data
        else:
            raise ValueError("Data must be a DataFrame")

        self.cov_matrix = returns.cov().values
        self.is_fitted = True
        logger.info(f"RiskParity model fitted with {len(returns)} observations")
        return self

    def optimize(self, returns: pd.DataFrame) -> np.ndarray:
        """优化风险平价组合

        Args:
            returns: 资产收益率DataFrame

        Returns:
            最优权重数组
        """
        if not self.is_fitted:
            self.fit(returns)

        method = self.params.get("method", "inverse_variance")

        if method == "inverse_variance":
            self.weights = self._inverse_variance_weights(self.cov_matrix)
        else:
            # 使用优化求解等风险贡献
            constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
            bounds = [
                (self.params["min_weight"], self.params["max_weight"])
                for _ in range(self.n_assets)
            ]
            initial_guess = np.ones(self.n_assets) / self.n_assets

            result = minimize(
                self._risk_parity_objective,
                initial_guess,
                args=(self.cov_matrix,),
                method="SLSQP",
                bounds=bounds,
                constraints=constraints
            )

            self.weights = result.x

        logger.debug(f"RiskParity weights: {dict(zip(self.assets, self.weights.round(4)))}")
        return self.weights

    def get_risk_contributions(self) -> pd.DataFrame:
        """获取各资产的风险贡献"""
        if self.weights is None or self.cov_matrix is None:
            raise ValueError("Model not fitted or optimized")

        risk_contrib = self._calculate_risk_contribution(self.weights, self.cov_matrix)
        risk_contrib_pct = risk_contrib / risk_contrib.sum() * 100

        return pd.DataFrame({
            "asset": self.assets,
            "weight": self.weights,
            "risk_contrib": risk_contrib,
            "risk_contrib_pct": risk_contrib_pct
        })

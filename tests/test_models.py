"""
模型层测试
"""

import numpy as np
import pandas as pd
import pytest

from models.allocation import RiskParityModel, MeanVarianceModel
from models.factor import FactorCalculator


class TestAllocationModels:
    """测试资产配置模型"""

    def test_risk_parity_basic(self):
        """测试风险平价基础功能"""
        assets = ["A", "B", "C"]
        model = RiskParityModel(assets)

        # 生成收益率数据
        np.random.seed(42)
        returns = pd.DataFrame(
            np.random.randn(100, 3) * 0.02,
            columns=assets
        )

        weights = model.optimize(returns)

        assert len(weights) == 3
        assert abs(weights.sum() - 1.0) < 1e-6
        assert all(w >= 0 for w in weights)

    def test_mean_variance_sharpe(self):
        """测试均值方差优化"""
        assets = ["A", "B", "C"]
        model = MeanVarianceModel(assets, params={"objective": "sharpe"})

        np.random.seed(42)
        returns = pd.DataFrame(
            np.random.randn(252, 3) * 0.02 + 0.0005,
            columns=assets
        )

        weights = model.optimize(returns)

        assert len(weights) == 3
        assert abs(weights.sum() - 1.0) < 1e-6


class TestFactorCalculator:
    """测试因子计算器"""

    def test_technical_factors(self):
        """测试技术面因子计算"""
        calc = FactorCalculator()

        # 生成价格数据
        dates = pd.date_range(start="2024-01-01", periods=100, freq="B")
        price_data = pd.DataFrame({
            "open": np.random.randn(100).cumsum() + 100,
            "high": np.random.randn(100).cumsum() + 101,
            "low": np.random.randn(100).cumsum() + 99,
            "close": np.random.randn(100).cumsum() + 100,
            "volume": np.random.randint(1000000, 10000000, 100)
        }, index=dates)

        factors = calc.calculate_technical_factors(price_data)

        assert not factors.empty
        assert "momentum_20d" in factors.columns
        assert "rsi_14d" in factors.columns

    def test_cross_sectional_rank(self):
        """测试截面排序"""
        calc = FactorCalculator()

        factor_data = pd.DataFrame({
            "pe": [10, 20, 30, 40, 50],
            "pb": [1, 2, 3, 4, 5]
        }, index=["A", "B", "C", "D", "E"])

        ranked = calc.cross_sectional_rank(
            factor_data,
            ["pe", "pb"],
            directions={"pe": -1, "pb": -1}  # 越小越好
        )

        assert "pe_rank" in ranked.columns
        assert "pb_rank" in ranked.columns
        # PE最小的A应该排名最高（最接近1）
        assert ranked.loc["A", "pe_rank"] > ranked.loc["E", "pe_rank"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
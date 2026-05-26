"""
模型层测试 - 期权相关
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from models.option import (
    BlackScholesModel,
    OptionContract,
    GreeksCalculator,
    VolatilityCalculator,
)


class TestBlackScholes:
    """测试Black-Scholes模型"""

    def test_call_option_price(self):
        """测试看涨期权定价"""
        # 平值看涨期权
        price = BlackScholesModel.price("call", 100, 100, 0.25, 0.05, 0.2)
        assert price > 0
        assert price < 100

        # ITM call
        itm_price = BlackScholesModel.price("call", 110, 100, 0.25, 0.05, 0.2)
        assert itm_price > price

        # OTM call
        otm_price = BlackScholesModel.price("call", 90, 100, 0.25, 0.05, 0.2)
        assert otm_price < price

    def test_put_call_parity(self):
        """测试看涨看跌平价关系"""
        spot, strike, time, rate, vol = 100, 100, 0.25, 0.05, 0.2

        call_price = BlackScholesModel.price("call", spot, strike, time, rate, vol)
        put_price = BlackScholesModel.price("put", spot, strike, time, rate, vol)

        # C - P = S - K * exp(-rT)
        lhs = call_price - put_price
        rhs = spot - strike * np.exp(-rate * time)

        assert abs(lhs - rhs) < 1e-6

    def test_greeks_properties(self):
        """测试希腊值性质"""
        spot, strike, time, rate, vol = 100, 100, 0.25, 0.05, 0.2

        # Delta range
        call_delta = BlackScholesModel.delta("call", spot, strike, time, rate, vol)
        put_delta = BlackScholesModel.delta("put", spot, strike, time, rate, vol)

        assert 0 < call_delta < 1
        assert -1 < put_delta < 0
        assert abs(call_delta - put_delta - 1) < 1e-6

        # Gamma positive
        gamma = BlackScholesModel.gamma(spot, strike, time, rate, vol)
        assert gamma > 0

        # Vega positive
        vega = BlackScholesModel.vega(spot, strike, time, rate, vol)
        assert vega > 0

    def test_expiry_behavior(self):
        """测试到期时行为"""
        spot, strike = 110, 100

        # ATM at expiry
        call_price = BlackScholesModel.price("call", spot, strike, 0, 0.05, 0.2)
        assert call_price == max(spot - strike, 0)

        put_price = BlackScholesModel.price("put", spot, strike, 0, 0.05, 0.2)
        assert put_price == max(strike - spot, 0)


class TestOptionContract:
    """测试期权合约类"""

    def test_contract_creation(self):
        """测试合约创建"""
        expiry = datetime.now() + timedelta(days=30)
        contract = OptionContract(
            symbol="510300_C_5200_202401",
            option_type="call",
            strike=5.2,
            expiry=expiry,
            underlying="510300.SH",
            multiplier=10000
        )

        assert contract.option_type == "call"
        assert contract.strike == 5.2
        assert contract.multiplier == 10000

    def test_time_to_maturity(self):
        """测试剩余期限计算"""
        expiry = datetime.now() + timedelta(days=30)
        contract = OptionContract(
            symbol="test",
            option_type="call",
            strike=100,
            expiry=expiry,
            underlying="TEST"
        )

        ttm = contract.time_to_maturity()
        assert 0 < ttm < 0.1  # 约30/365


class TestGreeksCalculator:
    """测试希腊值计算器"""

    def test_calculate_greeks(self):
        """测试希腊值计算"""
        calc = GreeksCalculator(rate=0.03)

        contract = OptionContract(
            symbol="test",
            option_type="call",
            strike=100,
            expiry=datetime.now() + timedelta(days=30),
            underlying="TEST"
        )

        greeks = calc.calculate(contract, spot=100, vol=0.25)

        assert isinstance(greeks.delta, float)
        assert isinstance(greeks.gamma, float)
        assert isinstance(greeks.vega, float)
        assert isinstance(greeks.theta, float)
        assert isinstance(greeks.rho, float)

    def test_portfolio_greeks(self):
        """测试组合希腊值"""
        calc = GreeksCalculator(rate=0.03)

        expiry = datetime.now() + timedelta(days=30)

        # 构建两个期权持仓
        positions = [
            (OptionContract("c1", "call", 100, expiry, "TEST"), 1, 100, 0.25),
            (OptionContract("p1", "put", 100, expiry, "TEST"), -1, 100, 0.25),
        ]

        portfolio_greeks = calc.calculate_portfolio(positions)

        # 多空组合应该部分对冲
        assert isinstance(portfolio_greeks, Greeks)


class TestVolatilityCalculator:
    """测试波动率计算器"""

    def test_historical_volatility(self):
        """测试历史波动率"""
        np.random.seed(42)
        returns = np.random.randn(100) * 0.02  # 2%日波动
        prices = pd.Series(100 * np.exp(np.cumsum(returns)))

        vol_calc = VolatilityCalculator()
        hv = vol_calc.historical_volatility(prices, window=20)

        assert hv > 0
        assert 0.1 < hv < 0.5  # 应该在合理范围

    def test_realized_volatility(self):
        """测试已实现波动率"""
        np.random.seed(42)
        returns = pd.Series(np.random.randn(100) * 0.02)

        vol_calc = VolatilityCalculator()
        rv = vol_calc.realized_volatility(returns)

        assert rv > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

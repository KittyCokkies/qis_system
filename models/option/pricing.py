from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal, Union

import numpy as np
from scipy.stats import norm
from loguru import logger


@dataclass
class OptionContract:
    """期权合约定义"""
    symbol: str
    option_type: Literal["call", "put"]  # 看涨/看跌
    strike: float                       # 行权价
    expiry: datetime                    # 到期日
    underlying: str                     # 标的代码
    multiplier: int = 10000             # 合约乘数（ETF期权通常为10000）

    def time_to_maturity(self, as_of: Optional[datetime] = None) -> float:
        """计算剩余期限（年化）"""
        if as_of is None:
            as_of = datetime.now()
        days = (self.expiry - as_of).days
        return max(days / 365.0, 0)


class BlackScholesModel:
    """Black-Scholes期权定价模型

    适用于欧式期权定价
    """

    @staticmethod
    def d1(
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算d1"""
        if time <= 0 or vol <= 0:
            return 0
        return (np.log(spot / strike) + (rate + 0.5 * vol ** 2) * time) / (vol * np.sqrt(time))

    @staticmethod
    def d2(
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算d2"""
        return BlackScholesModel.d1(spot, strike, time, rate, vol) - vol * np.sqrt(time)

    @classmethod
    def price(
        cls,
        option_type: Literal["call", "put"],
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算期权理论价格

        Args:
            option_type: 期权类型 call/put
            spot: 标的价格
            strike: 行权价
            time: 剩余期限（年化）
            rate: 无风险利率
            vol: 波动率

        Returns:
            期权价格
        """
        if time <= 0:
            # 到期时
            if option_type == "call":
                return max(spot - strike, 0)
            else:
                return max(strike - spot, 0)

        d1 = cls.d1(spot, strike, time, rate, vol)
        d2 = cls.d2(spot, strike, time, rate, vol)

        if option_type == "call":
            price = spot * norm.cdf(d1) - strike * np.exp(-rate * time) * norm.cdf(d2)
        else:
            price = strike * np.exp(-rate * time) * norm.cdf(-d2) - spot * norm.cdf(-d1)

        return price

    @classmethod
    def implied_volatility(
        cls,
        option_type: Literal["call", "put"],
        market_price: float,
        spot: float,
        strike: float,
        time: float,
        rate: float,
        initial_guess: float = 0.2,
        precision: float = 1e-5,
        max_iter: int = 100
    ) -> Optional[float]:
        """计算隐含波动率（Newton-Raphson方法）"""
        vol = initial_guess

        for i in range(max_iter):
            price = cls.price(option_type, spot, strike, time, rate, vol)
            diff = market_price - price

            if abs(diff) < precision:
                return vol

            # 计算vega
            vega = cls.vega(spot, strike, time, rate, vol)
            if vega == 0:
                return None

            vol = vol + diff / vega
            vol = max(0.001, min(vol, 5.0))  # 限制波动率范围

        logger.warning(f"Implied volatility did not converge after {max_iter} iterations")
        return None

    @classmethod
    def delta(
        cls,
        option_type: Literal["call", "put"],
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算Delta"""
        if time <= 0:
            if option_type == "call":
                return 1.0 if spot > strike else 0.0
            else:
                return -1.0 if spot < strike else 0.0

        d1 = cls.d1(spot, strike, time, rate, vol)
        if option_type == "call":
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1

    @classmethod
    def gamma(
        cls,
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算Gamma（call和put相同）"""
        if time <= 0 or vol <= 0:
            return 0

        d1 = cls.d1(spot, strike, time, rate, vol)
        return norm.pdf(d1) / (spot * vol * np.sqrt(time))

    @classmethod
    def vega(
        cls,
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算Vega（call和put相同）

        注意：这是每1%波动率变化的价格变化
        """
        if time <= 0 or vol <= 0:
            return 0

        d1 = cls.d1(spot, strike, time, rate, vol)
        return spot * norm.pdf(d1) * np.sqrt(time) / 100

    @classmethod
    def theta(
        cls,
        option_type: Literal["call", "put"],
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算Theta（每日时间衰减）"""
        if time <= 0:
            return 0

        d1 = cls.d1(spot, strike, time, rate, vol)
        d2 = cls.d2(spot, strike, time, rate, vol)

        first_term = -spot * norm.pdf(d1) * vol / (2 * np.sqrt(time))

        if option_type == "call":
            second_term = -rate * strike * np.exp(-rate * time) * norm.cdf(d2)
        else:
            second_term = rate * strike * np.exp(-rate * time) * norm.cdf(-d2)

        return (first_term + second_term) / 365

    @classmethod
    def rho(
        cls,
        option_type: Literal["call", "put"],
        spot: float,
        strike: float,
        time: float,
        rate: float,
        vol: float
    ) -> float:
        """计算Rho（利率敏感度）"""
        if time <= 0:
            return 0

        d2 = cls.d2(spot, strike, time, rate, vol)

        if option_type == "call":
            return strike * time * np.exp(-rate * time) * norm.cdf(d2) / 100
        else:
            return -strike * time * np.exp(-rate * time) * norm.cdf(-d2) / 100


class OptionPricer:
    """期权定价器

    提供更友好的接口
    """

    def __init__(self, rate: float = 0.03):
        self.rate = rate
        self.model = BlackScholesModel()

    def price(self, contract: OptionContract, spot: float, vol: float) -> float:
        """定价"""
        time = contract.time_to_maturity()
        return self.model.price(
            contract.option_type,
            spot,
            contract.strike,
            time,
            self.rate,
            vol
        )

    def implied_vol(
        self,
        contract: OptionContract,
        market_price: float,
        spot: float
    ) -> Optional[float]:
        """计算隐含波动率"""
        time = contract.time_to_maturity()
        return self.model.implied_volatility(
            contract.option_type,
            market_price,
            spot,
            contract.strike,
            time,
            self.rate
        )

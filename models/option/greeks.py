from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from models.option.pricing import BlackScholesModel, OptionContract


@dataclass
class Greeks:
    """希腊值数据类"""
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho
        }


class GreeksCalculator:
    """希腊值计算器"""

    def __init__(self, rate: float = 0.03):
        self.rate = rate

    def calculate(
        self,
        contract: OptionContract,
        spot: float,
        vol: float
    ) -> Greeks:
        """计算单个期权的希腊值"""
        time = contract.time_to_maturity()

        delta = BlackScholesModel.delta(
            contract.option_type, spot, contract.strike, time, self.rate, vol
        )
        gamma = BlackScholesModel.gamma(
            spot, contract.strike, time, self.rate, vol
        )
        vega = BlackScholesModel.vega(
            spot, contract.strike, time, self.rate, vol
        )
        theta = BlackScholesModel.theta(
            contract.option_type, spot, contract.strike, time, self.rate, vol
        )
        rho = BlackScholesModel.rho(
            contract.option_type, spot, contract.strike, time, self.rate, vol
        )

        return Greeks(delta, gamma, vega, theta, rho)

    def calculate_portfolio(
        self,
        positions: List[tuple],  # [(contract, quantity, spot, vol), ...]
    ) -> Greeks:
        """计算组合希腊值

        Args:
            positions: 持仓列表，每个元素为 (合约, 数量(正=多/负=空), 标的价格, 波动率)
        """
        total_delta = 0
        total_gamma = 0
        total_vega = 0
        total_theta = 0
        total_rho = 0

        for contract, qty, spot, vol in positions:
            greeks = self.calculate(contract, spot, vol)
            total_delta += greeks.delta * qty * contract.multiplier
            total_gamma += greeks.gamma * qty * contract.multiplier
            total_vega += greeks.vega * qty * contract.multiplier
            total_theta += greeks.theta * qty * contract.multiplier
            total_rho += greeks.rho * qty * contract.multiplier

        return Greeks(total_delta, total_gamma, total_vega, total_theta, total_rho)

    def scenario_analysis(
        self,
        contract: OptionContract,
        spot: float,
        vol: float,
        spot_range: float = 0.1,
        vol_range: float = 0.05,
        n_steps: int = 5
    ) -> pd.DataFrame:
        """情景分析

        计算不同标的价格和波动率组合下的期权价值和希腊值
        """
        results = []

        spot_changes = np.linspace(-spot_range, spot_range, n_steps)
        vol_changes = np.linspace(-vol_range, vol_range, n_steps)

        for spot_change in spot_changes:
            new_spot = spot * (1 + spot_change)
            for vol_change in vol_changes:
                new_vol = max(0.01, vol + vol_change)

                greeks = self.calculate(contract, new_spot, new_vol)
                price = BlackScholesModel.price(
                    contract.option_type,
                    new_spot,
                    contract.strike,
                    contract.time_to_maturity(),
                    self.rate,
                    new_vol
                )

                results.append({
                    "spot_change": spot_change,
                    "vol_change": vol_change,
                    "new_spot": new_spot,
                    "new_vol": new_vol,
                    "price": price,
                    "delta": greeks.delta,
                    "gamma": greeks.gamma,
                    "vega": greeks.vega,
                    "theta": greeks.theta,
                })

        return pd.DataFrame(results)

    def hedge_ratio(
        self,
        contract: OptionContract,
        spot: float,
        vol: float,
        hedge_type: str = "delta"
    ) -> float:
        """计算对冲比率

        Args:
            contract: 期权合约
            spot: 标的价格
            vol: 波动率
            hedge_type: 对冲类型 ("delta" 或 "gamma")

        Returns:
            需要的标的对冲数量
        """
        greeks = self.calculate(contract, spot, vol)

        if hedge_type == "delta":
            # Delta对冲：1份期权需要 -delta 份标的
            return -greeks.delta * contract.multiplier
        elif hedge_type == "gamma":
            # Gamma对冲通常需要用其他期权，这里简化处理
            logger.warning("Gamma hedge requires additional options")
            return 0
        else:
            raise ValueError(f"Unknown hedge type: {hedge_type}")

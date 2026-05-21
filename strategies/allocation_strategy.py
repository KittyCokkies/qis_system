from datetime import datetime
from typing import Any, Dict, List, Optional, Type

import numpy as np
import pandas as pd
from loguru import logger

from models.allocation import RiskParityModel, MeanVarianceModel
from models.base import AllocationModelBase
from strategies.base import SignalType, StrategyBase, StrategyResult


class AllocationStrategy(StrategyBase):
    """大类资产配置策略

    使用资产配置模型（风险平价、均值方差等）进行多资产组合配置
    """

    # 支持的模型类型映射
    MODEL_MAP = {
        "risk_parity": RiskParityModel,
        "mean_variance": MeanVarianceModel,
    }

    def __init__(
        self,
        name: str,
        symbols: List[str],
        model_type: str = "risk_parity",
        rebalance_freq: str = "M",  # D=日, W=周, M=月, Q=季
        lookback_days: int = 252,
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "model_type": model_type,
            "rebalance_freq": rebalance_freq,
            "lookback_days": lookback_days,
            "transaction_cost": 0.001,
            "min_weight_change": 0.05,  # 最小调仓阈值
        }
        if params:
            default_params.update(params)

        super().__init__(name, symbols, default_params)

        self.model: Optional[AllocationModelBase] = None
        self.model_type = model_type
        self.rebalance_freq = rebalance_freq
        self.lookback_days = lookback_days
        self.last_rebalance_date: Optional[datetime] = None
        self.current_weights: Optional[Dict[str, float]] = None

    def initialize(self) -> "AllocationStrategy":
        """初始化策略"""
        model_class = self.MODEL_MAP.get(self.model_type)
        if model_class is None:
            raise ValueError(f"Unknown model type: {self.model_type}")

        self.model = model_class(
            assets=self.symbols,
            params=self.params
        )

        self.is_initialized = True
        logger.info(f"AllocationStrategy '{self.name}' initialized with {self.model_type}")
        return self

    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理新数据并生成配置决策"""
        if not self.validate_data(data):
            return StrategyResult(timestamp=datetime.now())

        if not self.is_initialized:
            self.initialize()

        current_date = data.index[-1]

        # 检查是否需要再平衡
        if not self._should_rebalance(current_date):
            # 维持当前权重
            return StrategyResult(
                timestamp=current_date,
                weights=self.current_weights or {s: 1.0/len(self.symbols) for s in self.symbols},
                signals={s: SignalType.HOLD for s in self.symbols}
            )

        # 获取历史数据用于计算
        lookback_data = data.iloc[-self.lookback_days:] if len(data) > self.lookback_days else data

        # 计算收益率
        returns = lookback_data[self.symbols].pct_change().dropna()

        if returns.empty or len(returns) < 30:
            logger.warning("Insufficient data for optimization")
            return StrategyResult(timestamp=current_date)

        # 运行优化
        weights = self.model.optimize(returns)
        weights_dict = dict(zip(self.symbols, weights))

        # 生成调仓信号
        signals = self._generate_rebalance_signals(weights_dict)

        # 更新状态
        self.current_weights = weights_dict
        self.last_rebalance_date = current_date

        result = StrategyResult(
            timestamp=current_date,
            weights=weights_dict,
            signals=signals,
            metadata={
                "rebalanced": True,
                "model": self.model_type,
                "expected_return": self.model._portfolio_performance(weights)[0] if hasattr(self.model, '_portfolio_performance') else None,
                "expected_volatility": self.model._portfolio_performance(weights)[1] if hasattr(self.model, '_portfolio_performance') else None,
            }
        )

        self.update_result(result)
        logger.info(f"Rebalanced at {current_date}: {weights_dict}")

        return result

    def _should_rebalance(self, current_date: datetime) -> bool:
        """检查是否需要再平衡"""
        if self.last_rebalance_date is None:
            return True

        freq_map = {
            "D": 1,
            "W": 7,
            "M": 30,
            "Q": 90,
        }
        min_days = freq_map.get(self.rebalance_freq, 30)

        return (current_date - self.last_rebalance_date).days >= min_days

    def _generate_rebalance_signals(self, new_weights: Dict[str, float]) -> Dict[str, SignalType]:
        """生成调仓信号"""
        if self.current_weights is None:
            # 首次建仓
            return {s: SignalType.BUY if new_weights.get(s, 0) > 0 else SignalType.HOLD
                    for s in self.symbols}

        signals = {}
        min_change = self.params.get("min_weight_change", 0.05)

        for symbol in self.symbols:
            old_w = self.current_weights.get(symbol, 0)
            new_w = new_weights.get(symbol, 0)
            diff = new_w - old_w

            if abs(diff) < min_change:
                signals[symbol] = SignalType.HOLD
            elif diff > 0:
                signals[symbol] = SignalType.BUY
            else:
                signals[symbol] = SignalType.SELL

        return signals

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成信号接口"""
        result = self.on_data(data)
        return result.signals

    def get_current_allocation(self) -> Optional[Dict[str, float]]:
        """获取当前配置"""
        return self.current_weights

    def backtest(
        self,
        price_data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """简单回测

        Args:
            price_data: 价格数据，包含所有标的
            start_date: 回测开始日期
            end_date: 回测结束日期

        Returns:
            回测结果DataFrame
        """
        if start_date:
            price_data = price_data[price_data.index >= start_date]
        if end_date:
            price_data = price_data[price_data.index <= end_date]

        self.reset()
        self.initialize()

        results = []

        for i in range(self.lookback_days, len(price_data)):
            current_data = price_data.iloc[:i]
            result = self.on_data(current_data)
            results.append({
                "date": result.timestamp,
                "weights": result.weights,
                "rebalanced": result.metadata.get("rebalanced", False)
            })

        return pd.DataFrame(results)

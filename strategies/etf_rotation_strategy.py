from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from strategies.base import SignalType, StrategyBase, StrategyResult


class ETFRotationStrategy(StrategyBase):
    """ETF轮动策略

    基于动量/趋势在多个ETF之间进行轮动配置
    支持行业轮动、宽基轮动、跨境轮动等多种模式
    """

    def __init__(
        self,
        name: str,
        etfs: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "lookback_days": 20,           # 回看周期
            "momentum_window": 60,         # 动量计算周期
            "volatility_window": 20,       # 波动率计算周期
            "n_holdings": 3,               # 持有ETF数量
            "rebalance_freq": "W",         # 调仓频率
            "score_method": "momentum",    # 评分方法: momentum, risk_adj_momentum, dual_momentum
            "cash_proxy": None,            # 现金替代标的（如国债ETF）
            "momentum_threshold": 0,       # 动量阈值，低于此值则持有现金
        }
        if params:
            default_params.update(params)

        super().__init__(name, etfs, default_params)

        self.lookback_days = default_params["lookback_days"]
        self.n_holdings = default_params["n_holdings"]
        self.score_method = default_params["score_method"]
        self.current_holdings: List[str] = []
        self.last_rebalance_date: Optional[datetime] = None

    def initialize(self) -> "ETFRotationStrategy":
        """初始化策略"""
        self.is_initialized = True
        logger.info(f"ETFRotationStrategy '{self.name}' initialized: "
                   f"{len(self.symbols)} ETFs, top {self.n_holdings}")
        return self

    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理新数据"""
        if not self.validate_data(data):
            return StrategyResult(timestamp=datetime.now())

        if not self.is_initialized:
            self.initialize()

        current_date = data.index[-1]

        # 检查是否需要调仓
        if not self._should_rebalance(current_date):
            return StrategyResult(
                timestamp=current_date,
                signals={s: SignalType.HOLD for s in self.current_holdings},
                weights={s: 1.0/len(self.current_holdings) for s in self.current_holdings} if self.current_holdings else {}
            )

        # 计算ETF得分
        scores = self._calculate_scores(data)

        if scores.empty:
            logger.warning("No scores calculated")
            return StrategyResult(timestamp=current_date)

        # 选择得分最高的ETF
        selected_etfs = self._select_etfs(scores)

        # 检查动量阈值（可选）
        cash_proxy = self.params.get("cash_proxy")
        momentum_threshold = self.params.get("momentum_threshold", 0)

        # 如果最高分ETF的动量低于阈值，切换到现金
        if not selected_etfs.empty:
            best_score = scores.loc[selected_etfs[0], "score"]
            if best_score < momentum_threshold and cash_proxy:
                selected_etfs = [cash_proxy]

        # 生成权重（等权或按得分加权）
        weights = self._calculate_weights(scores, selected_etfs)

        # 生成信号
        signals = self._generate_signals(selected_etfs)

        self.current_holdings = selected_etfs
        self.last_rebalance_date = current_date

        result = StrategyResult(
            timestamp=current_date,
            signals=signals,
            weights=weights,
            metadata={
                "rebalanced": True,
                "selected_etfs": selected_etfs,
                "scores": scores["score"].to_dict()
            }
        )

        self.update_result(result)
        logger.info(f"Rebalanced at {current_date}: selected {selected_etfs}")

        return result

    def _calculate_scores(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算ETF得分"""
        scores = pd.DataFrame(index=self.symbols)

        for symbol in self.symbols:
            if symbol not in data.columns:
                continue

            price = data[symbol]
            returns = price.pct_change()

            # 计算动量
            momentum_window = self.params["momentum_window"]
            if len(price) >= momentum_window:
                momentum = (price.iloc[-1] / price.iloc[-momentum_window] - 1)
            else:
                momentum = 0

            # 计算波动率
            vol_window = self.params["volatility_window"]
            volatility = returns.tail(vol_window).std() * np.sqrt(252) if len(returns) >= vol_window else np.inf

            scores.loc[symbol, "momentum"] = momentum
            scores.loc[symbol, "volatility"] = volatility

        # 根据评分方法计算最终得分
        if self.score_method == "momentum":
            scores["score"] = scores["momentum"]
        elif self.score_method == "risk_adj_momentum":
            # 风险调整动量 = 动量 / 波动率
            scores["score"] = scores["momentum"] / scores["volatility"].replace(0, np.inf)
        elif self.score_method == "dual_momentum":
            # 双动量：绝对动量 + 相对动量排名
            scores["abs_momentum"] = scores["momentum"]
            scores["rel_momentum"] = scores["momentum"].rank(pct=True)
            scores["score"] = scores["abs_momentum"] * scores["rel_momentum"]
        else:
            scores["score"] = scores["momentum"]

        return scores.dropna(subset=["score"])

    def _select_etfs(self, scores: pd.DataFrame) -> List[str]:
        """选择得分最高的ETF"""
        n = min(self.n_holdings, len(scores))
        selected = scores.sort_values("score", ascending=False).head(n).index.tolist()
        return selected

    def _calculate_weights(
        self,
        scores: pd.DataFrame,
        selected_etfs: List[str]
    ) -> Dict[str, float]:
        """计算权重"""
        if not selected_etfs:
            return {}

        # 等权
        if len(selected_etfs) > 0:
            weight = 1.0 / len(selected_etfs)
            return {etf: weight for etf in selected_etfs}

        return {}

    def _generate_signals(self, selected_etfs: List[str]) -> Dict[str, SignalType]:
        """生成买卖信号"""
        signals = {}

        # 卖出的ETF
        for etf in self.current_holdings:
            if etf not in selected_etfs:
                signals[etf] = SignalType.SELL

        # 买入的ETF
        for etf in selected_etfs:
            if etf not in self.current_holdings:
                signals[etf] = SignalType.BUY
            else:
                signals[etf] = SignalType.HOLD

        return signals

    def _should_rebalance(self, current_date: datetime) -> bool:
        """检查是否需要调仓"""
        if self.last_rebalance_date is None:
            return True

        freq_map = {
            "D": 1,
            "W": 7,
            "M": 30,
        }
        min_days = freq_map.get(self.params.get("rebalance_freq", "W"), 7)

        return (current_date - self.last_rebalance_date).days >= min_days

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成信号接口"""
        result = self.on_data(data)
        return result.signals

    def get_current_holdings(self) -> List[str]:
        """获取当前持仓"""
        return self.current_holdings.copy()

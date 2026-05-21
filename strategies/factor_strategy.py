from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from models.factor import FactorCalculator
from models.base import FactorModelBase
from strategies.base import SignalType, StrategyBase, StrategyResult


class FactorStrategy(StrategyBase):
    """多因子选股策略

    基于多因子模型进行股票筛选和打分，定期调仓
    """

    def __init__(
        self,
        name: str,
        universe: List[str],  # 股票池
        factors: List[str],   # 使用的因子
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "rebalance_freq": "M",      # 调仓频率
            "lookback_days": 20,        # 因子计算回看天数
            "n_positions": 50,          # 持仓数量
            "factor_weights": None,     # 因子权重，None则等权
            "neutralize_industry": False,  # 是否行业中性化
            "winsorize": True,          # 是否去极值
            "long_only": True,          # 是否只做多
        }
        if params:
            default_params.update(params)

        super().__init__(name, universe, default_params)

        self.factors = factors
        self.factor_calculator = FactorCalculator()
        self.factor_weights = default_params["factor_weights"] or {f: 1.0/len(factors) for f in factors}
        self.last_rebalance_date: Optional[datetime] = None
        self.current_holdings: List[str] = []

    def initialize(self) -> "FactorStrategy":
        """初始化策略"""
        self.is_initialized = True
        logger.info(f"FactorStrategy '{self.name}' initialized with factors: {self.factors}")
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
                positions={s: 1 for s in self.current_holdings}
            )

        # 计算因子值
        factor_data = self._calculate_factors(data)

        if factor_data.empty:
            logger.warning("No factor data calculated")
            return StrategyResult(timestamp=current_date)

        # 因子预处理和打分
        ranked_data = self._process_factors(factor_data)

        # 选股
        selected_stocks = self._select_stocks(ranked_data)

        # 生成信号
        signals = self._generate_signals(selected_stocks)

        # 等权分配
        n = len(selected_stocks)
        weights = {s: 1.0/n for s in selected_stocks} if n > 0 else {}

        self.current_holdings = selected_stocks
        self.last_rebalance_date = current_date

        result = StrategyResult(
            timestamp=current_date,
            signals=signals,
            weights=weights,
            positions={s: 1 for s in selected_stocks},
            metadata={
                "rebalanced": True,
                "selected_stocks": selected_stocks,
                "factor_scores": ranked_data.get("score", pd.Series()).to_dict()
            }
        )

        self.update_result(result)
        logger.info(f"Rebalanced at {current_date}: selected {len(selected_stocks)} stocks")

        return result

    def _calculate_factors(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算因子值"""
        # 假设data包含所有股票的价格数据，格式为 MultiIndex (date, symbol) 或宽格式
        # 这里简化处理，假设data是价格数据

        factor_data = pd.DataFrame()

        for symbol in self.symbols:
            if symbol not in data.columns:
                continue

            price_series = data[symbol]
            returns = price_series.pct_change()

            factors = pd.Series(index=[symbol], name=price_series.index[-1])

            # 技术面因子
            for window in [20, 60]:
                factors[f"momentum_{window}d"] = price_series.pct_change(window).iloc[-1]
                factors[f"volatility_{window}d"] = returns.rolling(window).std().iloc[-1] * (252 ** 0.5)

            factor_data = pd.concat([factor_data, factors.to_frame().T])

        return factor_data

    def _process_factors(self, factor_data: pd.DataFrame) -> pd.DataFrame:
        """处理因子数据"""
        # 去极值
        if self.params.get("winsorize"):
            for col in factor_data.columns:
                if col in self.factors:
                    factor_data[col] = self.factor_calculator.winsorize(factor_data[col])

        # 截面排序
        ranked_data = self.factor_calculator.cross_sectional_rank(
            factor_data,
            self.factors,
            directions={f: 1 for f in self.factors}  # 假设都是正向因子
        )

        # 合成得分
        ranked_data["score"] = self.factor_calculator.combine_factors(
            ranked_data,
            weights=self.factor_weights
        )

        return ranked_data

    def _select_stocks(self, ranked_data: pd.DataFrame) -> List[str]:
        """根据得分选股"""
        n = self.params.get("n_positions", 50)

        # 按得分排序，选择前n个
        selected = ranked_data.sort_values("score", ascending=False).head(n).index.tolist()

        return selected

    def _generate_signals(self, selected_stocks: List[str]) -> Dict[str, SignalType]:
        """生成买卖信号"""
        signals = {}

        # 卖出的股票
        for s in self.current_holdings:
            if s not in selected_stocks:
                signals[s] = SignalType.SELL

        # 买入的股票
        for s in selected_stocks:
            if s not in self.current_holdings:
                signals[s] = SignalType.BUY
            else:
                signals[s] = SignalType.HOLD

        return signals

    def _should_rebalance(self, current_date: datetime) -> bool:
        """检查是否需要调仓"""
        if self.last_rebalance_date is None:
            return True

        freq_map = {
            "D": 1,
            "W": 7,
            "M": 30,
            "Q": 90,
        }
        min_days = freq_map.get(self.params.get("rebalance_freq", "M"), 30)

        return (current_date - self.last_rebalance_date).days >= min_days

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成信号接口"""
        result = self.on_data(data)
        return result.signals

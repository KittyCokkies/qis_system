from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from backtest.context import BacktestContext
from backtest.portfolio import Portfolio
from backtest.metrics import PerformanceMetrics
from strategies.base import StrategyBase, StrategyResult


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    returns: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float]
    equity_curve: pd.Series

    def summary(self) -> str:
        """生成回测摘要"""
        return f"""
========== Backtest Summary ==========
Strategy: {self.strategy_name}
Period: {self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')}
Total Return: {self.metrics.get('total_return', 0):.2%}
Annual Return: {self.metrics.get('annual_return', 0):.2%}
Sharpe Ratio: {self.metrics.get('sharpe_ratio', 0):.2f}
Max Drawdown: {self.metrics.get('max_drawdown', 0):.2%}
Volatility: {self.metrics.get('volatility', 0):.2%}
=====================================
        """


class BacktestEngine:
    """回测引擎

    支持向量化回测和事件驱动回测两种模式
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
        mode: str = "event_driven"  # event_driven or vectorized
    ):
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.mode = mode

        self.context: Optional[BacktestContext] = None
        self.portfolio: Optional[Portfolio] = None
        self.results: List[StrategyResult] = []

        logger.info(f"BacktestEngine initialized: mode={mode}, initial_cash={initial_cash:,.2f}")

    def run(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """运行回测

        Args:
            strategy: 策略实例
            data: 历史数据
            start_date: 回测开始日期
            end_date: 回测结束日期

        Returns:
            回测结果
        """
        if self.mode == "event_driven":
            return self._run_event_driven(strategy, data, start_date, end_date)
        else:
            return self._run_vectorized(strategy, data, start_date, end_date)

    def _run_event_driven(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """事件驱动回测"""
        # 数据过滤
        if start_date:
            data = data[data.index >= start_date]
        if end_date:
            data = data[data.index <= end_date]

        if data.empty:
            raise ValueError("No data available for backtest")

        # 初始化上下文和组合
        self.context = BacktestContext(
            initial_cash=self.initial_cash,
            start_date=data.index[0]
        )
        self.portfolio = Portfolio(
            initial_cash=self.initial_cash,
            commission_rate=self.commission_rate,
            slippage=self.slippage
        )

        self.results = []

        # 逐日运行
        for i in range(len(data)):
            current_data = data.iloc[:i+1]
            current_date = data.index[i]

            # 更新组合市值
            current_prices = self._extract_prices(current_data)
            self.portfolio.update_market_value(current_prices, current_date)

            # 运行策略
            result = strategy.on_data(current_data)
            self.results.append(result)

            # 执行交易
            self._execute_signals(result, current_prices, current_date)

            # 更新上下文
            self.context.update(
                date=current_date,
                portfolio_value=self.portfolio.total_value,
                positions=self.portfolio.positions.copy(),
                cash=self.portfolio.cash
            )

        # 生成回测结果
        return self._generate_result(strategy.name, data)

    def _run_vectorized(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """向量化回测（快速）"""
        # 这里可以集成 VectorBT 或自定义向量化回测逻辑
        raise NotImplementedError("Vectorized backtest mode not yet implemented")

    def _extract_prices(self, data: pd.DataFrame) -> Dict[str, float]:
        """从数据中提取当前价格"""
        prices = {}
        for col in data.columns:
            if isinstance(col, str):
                # 假设收盘价列名为 symbol_close 或 symbol
                if col.endswith("_close"):
                    symbol = col.replace("_close", "")
                    prices[symbol] = data[col].iloc[-1]
                elif col in ["close"]:
                    prices["default"] = data[col].iloc[-1]
        return prices

    def _execute_signals(
        self,
        result: StrategyResult,
        prices: Dict[str, float],
        date: datetime
    ):
        """执行交易信号"""
        for symbol, signal in result.signals.items():
            if symbol not in prices:
                continue

            price = prices[symbol]

            if signal.name == "BUY":
                # 计算买入数量
                available_cash = self.portfolio.cash * 0.95  # 预留部分现金
                shares = int(available_cash / (price * (1 + self.slippage)))
                if shares > 0:
                    self.portfolio.buy(symbol, shares, price, date)

            elif signal.name == "SELL":
                # 卖出全部持仓
                shares = self.portfolio.positions.get(symbol, 0)
                if shares > 0:
                    self.portfolio.sell(symbol, shares, price, date)

            elif signal.name == "REBALANCE":
                # 再平衡
                target_weight = result.weights.get(symbol, 0)
                self.portfolio.rebalance(symbol, target_weight, price, date)

    def _generate_result(
        self,
        strategy_name: str,
        data: pd.DataFrame
    ) -> BacktestResult:
        """生成回测结果"""
        # 计算收益率
        equity_curve = self.context.get_equity_curve()
        returns = equity_curve.pct_change().dropna()

        # 计算绩效指标
        metrics_calc = PerformanceMetrics(returns)
        metrics = {
            "total_return": metrics_calc.total_return(),
            "annual_return": metrics_calc.annual_return(),
            "sharpe_ratio": metrics_calc.sharpe_ratio(),
            "max_drawdown": metrics_calc.max_drawdown(),
            "volatility": metrics_calc.volatility(),
            "calmar_ratio": metrics_calc.calmar_ratio(),
            "win_rate": metrics_calc.win_rate(),
            "profit_factor": metrics_calc.profit_factor(),
        }

        # 交易记录
        trades = pd.DataFrame(self.portfolio.trade_history)

        # 持仓记录
        positions = self.context.get_positions_history()

        result = BacktestResult(
            strategy_name=strategy_name,
            start_date=data.index[0],
            end_date=data.index[-1],
            returns=returns,
            positions=positions,
            trades=trades,
            metrics=metrics,
            equity_curve=equity_curve
        )

        logger.info(f"Backtest completed:\n{result.summary()}")
        return result

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from strategies.base import SignalType, StrategyBase, StrategyResult


class CTAStrategy(StrategyBase):
    """CTA策略

    商品期货趋势跟踪策略，支持多种信号生成方式
    """

    def __init__(
        self,
        name: str,
        symbols: List[str],
        signal_type: str = "trend_following",  # trend_following, mean_reversion, breakout
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "fast_window": 10,
            "slow_window": 30,
            "atr_window": 14,
            "atr_multiplier": 2.0,
            "position_size": 1.0,
            "stop_loss_atr": 2.0,
            "take_profit_atr": 4.0,
            "trailing_stop": False,
        }
        if params:
            default_params.update(params)

        super().__init__(name, symbols, default_params)

        self.signal_type = signal_type
        self.positions: Dict[str, int] = {s: 0 for s in symbols}
        self.entry_prices: Dict[str, Optional[float]] = {s: None for s in symbols}

    def initialize(self) -> "CTAStrategy":
        """初始化策略"""
        self.is_initialized = True
        logger.info(f"CTAStrategy '{self.name}' initialized: {self.signal_type}")
        return self

    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理新数据并生成交易信号"""
        if not self.validate_data(data):
            return StrategyResult(timestamp=datetime.now())

        if not self.is_initialized:
            self.initialize()

        current_date = data.index[-1]
        signals = {}
        new_positions = {}

        for symbol in self.symbols:
            if symbol not in data.columns:
                continue

            # 获取标的的数据
            symbol_data = data[[col for col in data.columns if symbol in col or col in ['open', 'high', 'low', 'close', 'volume']]]
            if symbol_data.empty:
                continue

            # 生成信号
            signal = self._generate_signal_for_symbol(symbol_data, symbol)

            # 检查止损止盈
            signal = self._check_stops(symbol, signal, symbol_data)

            signals[symbol] = signal
            new_positions[symbol] = self._calculate_position(symbol, signal)

        self.positions.update(new_positions)

        result = StrategyResult(
            timestamp=current_date,
            signals=signals,
            positions=self.positions.copy(),
            metadata={
                "signal_type": self.signal_type,
                "entry_prices": self.entry_prices.copy()
            }
        )

        self.update_result(result)
        return result

    def _generate_signal_for_symbol(self, data: pd.DataFrame, symbol: str) -> SignalType:
        """为单个标的生成信号"""
        if len(data) < self.params["slow_window"]:
            return SignalType.HOLD

        if self.signal_type == "trend_following":
            return self._trend_following_signal(data)
        elif self.signal_type == "mean_reversion":
            return self._mean_reversion_signal(data)
        elif self.signal_type == "breakout":
            return self._breakout_signal(data)
        else:
            return SignalType.HOLD

    def _trend_following_signal(self, data: pd.DataFrame) -> SignalType:
        """趋势跟踪信号（双均线）"""
        close = data["close"] if "close" in data.columns else data.iloc[:, 0]

        fast_ma = close.rolling(self.params["fast_window"]).mean().iloc[-1]
        slow_ma = close.rolling(self.params["slow_window"]).mean().iloc[-1]
        prev_fast = close.rolling(self.params["fast_window"]).mean().iloc[-2]
        prev_slow = close.rolling(self.params["slow_window"]).mean().iloc[-2]

        current_price = close.iloc[-1]

        # 金叉买入
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            return SignalType.BUY
        # 死叉卖出
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            return SignalType.SELL
        else:
            return SignalType.HOLD

    def _mean_reversion_signal(self, data: pd.DataFrame) -> SignalType:
        """均值回归信号（RSI超买超卖）"""
        close = data["close"] if "close" in data.columns else data.iloc[:, 0]

        # 计算RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        current_rsi = rsi.iloc[-1]

        if current_rsi < 30:  # 超卖买入
            return SignalType.BUY
        elif current_rsi > 70:  # 超买卖出
            return SignalType.SELL
        else:
            return SignalType.HOLD

    def _breakout_signal(self, data: pd.DataFrame) -> SignalType:
        """突破信号（唐奇安通道）"""
        high = data["high"] if "high" in data.columns else data.iloc[:, 0]
        low = data["low"] if "low" in data.columns else data.iloc[:, 0]
        close = data["close"] if "close" in data.columns else data.iloc[:, 0]

        window = self.params["slow_window"]

        upper_channel = high.rolling(window).max().iloc[-2]  # 昨日最高点
        lower_channel = low.rolling(window).min().iloc[-2]   # 昨日最低点
        current_price = close.iloc[-1]

        if current_price > upper_channel:  # 向上突破
            return SignalType.BUY
        elif current_price < lower_channel:  # 向下突破
            return SignalType.SELL
        else:
            return SignalType.HOLD

    def _calculate_atr(self, data: pd.DataFrame, window: int = 14) -> float:
        """计算ATR"""
        high = data["high"] if "high" in data.columns else data.iloc[:, 0]
        low = data["low"] if "low" in data.columns else data.iloc[:, 0]
        close = data["close"] if "close" in data.columns else data.iloc[:, 0]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]

        return atr

    def _check_stops(self, symbol: str, signal: SignalType, data: pd.DataFrame) -> SignalType:
        """检查止损止盈"""
        if self.positions.get(symbol, 0) == 0:
            return signal

        if self.entry_prices.get(symbol) is None:
            return signal

        close = data["close"] if "close" in data.columns else data.iloc[:, 0]
        current_price = close.iloc[-1]
        entry_price = self.entry_prices[symbol]

        atr = self._calculate_atr(data)

        # 止损
        stop_loss = self.params["stop_loss_atr"] * atr
        # 止盈
        take_profit = self.params["take_profit_atr"] * atr

        position = self.positions[symbol]

        if position > 0:  # 多头
            if current_price < entry_price - stop_loss:
                return SignalType.SELL
            if current_price > entry_price + take_profit:
                return SignalType.SELL
        elif position < 0:  # 空头
            if current_price > entry_price + stop_loss:
                return SignalType.BUY
            if current_price < entry_price - take_profit:
                return SignalType.BUY

        return signal

    def _calculate_position(self, symbol: str, signal: SignalType) -> int:
        """计算目标仓位"""
        current_position = self.positions.get(symbol, 0)

        if signal == SignalType.BUY:
            if current_position <= 0:
                # 开多或平空开多
                self.entry_prices[symbol] = None  # 将在成交时更新
                return 1
        elif signal == SignalType.SELL:
            if current_position >= 0:
                # 开空或平多开空
                self.entry_prices[symbol] = None
                return -1
        elif signal == SignalType.HOLD:
            return current_position

        return current_position

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成信号接口"""
        result = self.on_data(data)
        return result.signals

    def update_entry_price(self, symbol: str, price: float):
        """更新入场价格（用于记录实际成交价格）"""
        self.entry_prices[symbol] = price

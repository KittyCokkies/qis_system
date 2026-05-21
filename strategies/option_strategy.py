from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from models.option.pricing import OptionContract, OptionPricer
from models.option.greeks import GreeksCalculator, Greeks
from strategies.base import SignalType, StrategyBase, StrategyResult


@dataclass
class OptionPosition:
    """期权持仓"""
    contract: OptionContract
    quantity: int  # 正=多头，负=空头
    entry_price: float
    entry_date: datetime
    current_price: Optional[float] = None
    current_greeks: Optional[Greeks] = None

    @property
    def market_value(self) -> float:
        """市值"""
        if self.current_price is None:
            return 0
        return self.current_price * self.quantity * self.contract.multiplier

    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏"""
        if self.current_price is None:
            return 0
        return (self.current_price - self.entry_price) * self.quantity * self.contract.multiplier


class OptionStrategyBase(StrategyBase):
    """期权策略基类

    专门用于期权策略的基类，提供期权特有的功能
    """

    def __init__(
        self,
        name: str,
        underlying: str,
        params: Optional[Dict[str, Any]] = None
    ):
        super().__init__(name, [underlying], params)
        self.underlying = underlying
        self.option_positions: List[OptionPosition] = []
        self.pricer = OptionPricer(rate=self.params.get("risk_free_rate", 0.03))
        self.greeks_calc = GreeksCalculator(rate=self.params.get("risk_free_rate", 0.03))

    @abstractmethod
    def select_option(self, data: pd.DataFrame) -> Optional[OptionContract]:
        """选择期权合约"""
        pass

    @abstractmethod
    def should_adjust(self, data: pd.DataFrame) -> bool:
        """检查是否需要调仓/平仓"""
        pass

    def calculate_portfolio_greeks(self, spot: float, vol: float) -> Greeks:
        """计算组合希腊值"""
        positions = [
            (pos.contract, pos.quantity, spot, vol)
            for pos in self.option_positions
        ]
        return self.greeks_calc.calculate_portfolio(positions)

    def find_option_by_criteria(
        self,
        options_chain: pd.DataFrame,
        delta_target: Optional[float] = None,
        dte_target: Optional[int] = None,
        option_type: str = "call"
    ) -> Optional[OptionContract]:
        """根据条件从期权链中选择合约

        Args:
            options_chain: 期权链数据
            delta_target: 目标delta
            dte_target: 目标到期天数
            option_type: 期权类型

        Returns:
            选中的期权合约
        """
        if options_chain.empty:
            return None

        chain = options_chain[options_chain["option_type"] == option_type].copy()

        if delta_target is not None:
            chain["delta_diff"] = abs(chain["delta"] - delta_target)
            chain = chain.sort_values("delta_diff")

        if dte_target is not None:
            chain["dte"] = (chain["expiry"] - datetime.now()).dt.days
            chain["dte_diff"] = abs(chain["dte"] - dte_target)
            chain = chain.sort_values("dte_diff")

        if chain.empty:
            return None

        row = chain.iloc[0]
        return OptionContract(
            symbol=row["symbol"],
            option_type=option_type,
            strike=row["strike"],
            expiry=row["expiry"],
            underlying=self.underlying,
            multiplier=row.get("multiplier", 10000)
        )

    def generate_option_signals(self, data: pd.DataFrame) -> Dict[str, Any]:
        """生成期权交易信号

        返回结构：
        {
            "action": "open" / "close" / "roll" / "hold",
            "contracts": [...],  # 涉及合约
            "quantities": [...], # 对应数量
            "reason": str       # 信号原因
        }
        """
        pass


class CoveredCallStrategy(OptionStrategyBase):
    """备兑开仓策略 (Covered Call)

    持有标的现货 + 卖出看涨期权
    适合震荡或温和上涨行情，增强收益
    """

    def __init__(
        self,
        name: str,
        underlying: str,
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "target_delta": 0.3,        # 目标delta（虚值程度）
            "dte_target": 30,           # 目标到期天数
            "dte_min": 7,               # 最少剩余天数（提前平仓阈值）
            "profit_take_pct": 0.5,     # 盈利50%时止盈
            "max_loss_pct": 2.0,        # 最大亏损百分比（标的下跌）
            "lot_size": 10000,          # 每手标的数量
            "max_positions": 1,         # 最大持仓数量
        }
        if params:
            default_params.update(params)

        super().__init__(name, underlying, default_params)

        self.stock_position: int = 0  # 标的持仓数量
        self.short_call: Optional[OptionPosition] = None  # 卖出的看涨期权

    def initialize(self) -> "CoveredCallStrategy":
        """初始化策略"""
        self.is_initialized = True
        logger.info(f"CoveredCall strategy initialized for {self.underlying}")
        return self

    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理数据并生成交易决策"""
        if not self.validate_data(data):
            return StrategyResult(timestamp=datetime.now())

        if not self.is_initialized:
            self.initialize()

        current_date = data.index[-1]
        current_price = data[self.underlying].iloc[-1] if self.underlying in data.columns else data["close"].iloc[-1]

        # 获取当前波动率（实际应从数据中计算或获取隐含波动率）
        current_vol = self._estimate_volatility(data)

        # 更新持仓希腊值
        self._update_positions(current_price, current_vol)

        # 生成交易信号
        signal_info = self._generate_signals(data, current_price, current_vol)

        # 构建结果
        result = StrategyResult(
            timestamp=current_date,
            signals={self.underlying: signal_info.get("stock_signal", SignalType.HOLD)},
            positions={
                self.underlying: self.stock_position,
                "short_call": self.short_call.quantity if self.short_call else 0
            },
            metadata={
                "action": signal_info.get("action"),
                "reason": signal_info.get("reason"),
                "current_price": current_price,
                "current_vol": current_vol,
                "portfolio_greeks": self.calculate_portfolio_greeks(current_price, current_vol).to_dict() if self.short_call else None,
                "short_call_pnl": self.short_call.unrealized_pnl if self.short_call else 0,
            }
        )

        self.update_result(result)
        return result

    def _estimate_volatility(self, data: pd.DataFrame) -> float:
        """估计波动率（简化）"""
        if self.underlying in data.columns:
            prices = data[self.underlying]
        elif "close" in data.columns:
            prices = data["close"]
        else:
            return 0.2

        returns = np.log(prices / prices.shift(1)).dropna()
        return returns.tail(20).std() * np.sqrt(252)

    def _update_positions(self, spot: float, vol: float):
        """更新持仓市值和希腊值"""
        if self.short_call:
            self.short_call.current_price = self.pricer.price(self.short_call.contract, spot, vol)
            self.short_call.current_greeks = self.greeks_calc.calculate(self.short_call.contract, spot, vol)

    def _generate_signals(
        self,
        data: pd.DataFrame,
        spot: float,
        vol: float
    ) -> Dict[str, Any]:
        """生成交易信号"""

        # 情况1：没有持仓 - 建仓
        if self.stock_position == 0 and self.short_call is None:
            return self._build_position(spot, vol, data)

        # 情况2：有现货但没有期权 - 卖出看涨
        if self.stock_position > 0 and self.short_call is None:
            return self._sell_call(spot, vol, data)

        # 情况3：有完整备兑持仓 - 检查是否需要调整
        if self.short_call:
            return self._manage_position(spot, vol, data)

        return {"action": "hold", "reason": "no_action"}

    def _build_position(self, spot: float, vol: float, data: pd.DataFrame) -> Dict[str, Any]:
        """建立新仓位"""
        # 买入标的
        lot_size = self.params["lot_size"]

        return {
            "action": "open",
            "stock_signal": SignalType.BUY,
            "stock_quantity": lot_size,
            "reason": "initiate_covered_call",
            "note": f"Buy {lot_size} shares of {self.underlying}"
        }

    def _sell_call(self, spot: float, vol: float, data: pd.DataFrame) -> Dict[str, Any]:
        """卖出看涨期权"""
        # 实际应用中，这里应该从期权链中选择合适的合约
        # 简化处理：根据参数计算行权价

        target_delta = self.params["target_delta"]
        dte_target = self.params["dte_target"]

        # 根据delta估算行权价（简化）
        # 实际应该从期权链数据中选择最接近的
        strike = spot * 1.05  # 虚值5%

        expiry = datetime.now() + pd.Timedelta(days=dte_target)

        contract = OptionContract(
            symbol=f"{self.underlying}_call_{strike}_{expiry.strftime('%Y%m')}",
            option_type="call",
            strike=strike,
            expiry=expiry,
            underlying=self.underlying
        )

        option_price = self.pricer.price(contract, spot, vol)

        # 记录持仓
        self.short_call = OptionPosition(
            contract=contract,
            quantity=-1,  # 空头
            entry_price=option_price,
            entry_date=datetime.now(),
            current_price=option_price
        )

        return {
            "action": "sell_call",
            "stock_signal": SignalType.HOLD,
            "option_contract": contract,
            "option_quantity": -1,
            "reason": "sell_otm_call",
            "premium_received": option_price * contract.multiplier,
            "note": f"Sell Call K={strike:.2f} @ {option_price:.4f}"
        }

    def _manage_position(
        self,
        spot: float,
        vol: float,
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """管理现有仓位"""
        call_pos = self.short_call

        # 检查1：盈利止盈（权利金收入超过50%）
        if call_pos.entry_price > 0:
            profit_pct = (call_pos.entry_price - call_pos.current_price) / call_pos.entry_price
            if profit_pct >= self.params["profit_take_pct"]:
                return self._close_call("profit_take", spot)

        # 检查2：临近到期
        dte = call_pos.contract.time_to_maturity() * 365
        if dte <= self.params["dte_min"]:
            return self._roll_or_close(spot, vol, data)

        # 检查3：标的深度下跌（止损）
        entry_spot = call_pos.entry_price  # 简化：用期权价格代替
        spot_decline = (entry_spot - spot) / entry_spot if entry_spot > 0 else 0
        if spot_decline > self.params["max_loss_pct"]:
            return self._close_entire_position("stop_loss", spot)

        # 检查4：深度实值（考虑roll up）
        if spot > call_pos.contract.strike * 1.05:
            return self._roll_up(spot, vol, data)

        return {"action": "hold", "reason": "monitoring"}

    def _close_call(self, reason: str, spot: float) -> Dict[str, Any]:
        """平仓看涨期权"""
        pnl = self.short_call.unrealized_pnl
        self.short_call = None

        return {
            "action": "close_call",
            "stock_signal": SignalType.HOLD,
            "reason": reason,
            "realized_pnl": pnl,
            "note": f"Close short call: {reason}"
        }

    def _close_entire_position(self, reason: str, spot: float) -> Dict[str, Any]:
        """平掉整个仓位"""
        return {
            "action": "close_all",
            "stock_signal": SignalType.SELL,
            "stock_quantity": -self.stock_position,
            "reason": reason,
            "note": f"Close entire position: {reason}"
        }

    def _roll_or_close(self, spot: float, vol: float, data: pd.DataFrame) -> Dict[str, Any]:
        """到期处理：展期或平仓"""
        # 简化：直接平仓
        return self._close_call("expiry_approaching", spot)

    def _roll_up(self, spot: float, vol: float, data: pd.DataFrame) -> Dict[str, Any]:
        """向上展期（标的大幅上涨）"""
        # 先平仓旧期权
        old_call = self.short_call
        old_pnl = old_call.unrealized_pnl if old_call else 0

        self.short_call = None

        return {
            "action": "roll_up",
            "stock_signal": SignalType.HOLD,
            "reason": "deep_itm",
            "old_pnl": old_pnl,
            "note": "Roll up call option to capture more upside"
        }

    def select_option(self, data: pd.DataFrame) -> Optional[OptionContract]:
        """选择期权合约接口"""
        return None  # 已实现内部逻辑

    def should_adjust(self, data: pd.DataFrame) -> bool:
        """检查是否需要调整"""
        return True  # 已实现内部逻辑

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成信号接口"""
        result = self.on_data(data)
        return result.signals

    def get_max_profit(self) -> float:
        """计算最大盈利"""
        if not self.short_call or self.stock_position == 0:
            return float('inf')

        strike = self.short_call.contract.strike
        premium = self.short_call.entry_price
        # 简化计算，实际需要知道建仓时的标的价格
        return (strike - 100 + premium) * abs(self.short_call.quantity) * self.short_call.contract.multiplier

    def get_break_even(self) -> Optional[float]:
        """计算盈亏平衡点"""
        if not self.short_call:
            return None

        # 简化计算
        premium = self.short_call.entry_price
        return 100 - premium  # 假设建仓时标的价格为100

    def calculate_yield_enhancement(self, spot: float) -> Dict[str, float]:
        """计算收益增强效果"""
        if not self.short_call:
            return {"monthly_yield": 0, "annual_yield": 0}

        days_to_expiry = self.short_call.contract.time_to_maturity() * 365
        premium = self.short_call.entry_price * self.short_call.contract.multiplier
        notional = spot * self.params["lot_size"]

        monthly_yield = premium / notional if notional > 0 else 0
        annual_yield = monthly_yield * (365 / max(days_to_expiry, 1))

        return {
            "monthly_yield": monthly_yield,
            "annual_yield": annual_yield,
            "premium_amount": premium
        }


class VolCarryStrategy(OptionStrategyBase):
    """波动率套利策略 (Volatility Carry)

    利用期权期限结构或波动率偏斜进行套利
    常见策略：日历价差、波动率做空等
    """

    def __init__(
        self,
        name: str,
        underlying: str,
        params: Optional[Dict[str, Any]] = None
    ):
        default_params = {
            "strategy_type": "calendar_spread",  # calendar_spread, strangle, iron_condor
            "front_dte": 30,           # 近月到期天数
            "back_dte": 60,            # 远月到期天数
            "target_delta": 0.3,       # 目标delta（虚值程度）
            "vol_spread_threshold": 0.03,  # 波动率价差阈值
            "profit_take": 0.5,        # 50%止盈
            "stop_loss": 2.0,          # 200%止损
        }
        if params:
            default_params.update(params)

        super().__init__(name, underlying, default_params)

        self.front_position: Optional[OptionPosition] = None  # 近月
        self.back_position: Optional[OptionPosition] = None   # 远月
        self.strategy_type = self.params["strategy_type"]

    def initialize(self) -> "VolCarryStrategy":
        """初始化策略"""
        self.is_initialized = True
        logger.info(f"VolCarry strategy initialized: {self.strategy_type}")
        return self

    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理数据"""
        if not self.validate_data(data):
            return StrategyResult(timestamp=datetime.now())

        if not self.is_initialized:
            self.initialize()

        current_date = data.index[-1]
        current_price = data[self.underlying].iloc[-1] if self.underlying in data.columns else data["close"].iloc[-1]
        current_vol = self._estimate_volatility(data)

        # 更新持仓
        self._update_positions(current_price, current_vol)

        # 生成信号
        signal_info = self._generate_signals(data, current_price, current_vol)

        result = StrategyResult(
            timestamp=current_date,
            signals={self.underlying: SignalType.HOLD},
            positions={
                "front": self.front_position.quantity if self.front_position else 0,
                "back": self.back_position.quantity if self.back_position else 0,
            },
            metadata={
                "action": signal_info.get("action"),
                "reason": signal_info.get("reason"),
                "net_theta": self._get_net_theta(),
                "net_vega": self._get_net_vega(),
                "unrealized_pnl": self._get_unrealized_pnl(),
            }
        )

        self.update_result(result)
        return result

    def _estimate_volatility(self, data: pd.DataFrame) -> float:
        """估计波动率"""
        if self.underlying in data.columns:
            prices = data[self.underlying]
        elif "close" in data.columns:
            prices = data["close"]
        else:
            return 0.2

        returns = np.log(prices / prices.shift(1)).dropna()
        return returns.tail(20).std() * np.sqrt(252)

    def _update_positions(self, spot: float, vol: float):
        """更新持仓"""
        for pos in [self.front_position, self.back_position]:
            if pos:
                pos.current_price = self.pricer.price(pos.contract, spot, vol)
                pos.current_greeks = self.greeks_calc.calculate(pos.contract, spot, vol)

    def _get_net_theta(self) -> float:
        """计算净Theta"""
        theta = 0
        if self.front_position and self.front_position.current_greeks:
            theta += self.front_position.current_greeks.theta * self.front_position.quantity
        if self.back_position and self.back_position.current_greeks:
            theta += self.back_position.current_greeks.theta * self.back_position.quantity
        return theta

    def _get_net_vega(self) -> float:
        """计算净Vega"""
        vega = 0
        if self.front_position and self.front_position.current_greeks:
            vega += self.front_position.current_greeks.vega * self.front_position.quantity
        if self.back_position and self.back_position.current_greeks:
            vega += self.back_position.current_greeks.vega * self.back_position.quantity
        return vega

    def _get_unrealized_pnl(self) -> float:
        """计算未实现盈亏"""
        pnl = 0
        if self.front_position:
            pnl += self.front_position.unrealized_pnl
        if self.back_position:
            pnl += self.back_position.unrealized_pnl
        return pnl

    def _generate_signals(
        self,
        data: pd.DataFrame,
        spot: float,
        vol: float
    ) -> Dict[str, Any]:
        """生成交易信号"""

        # 检查是否需要平仓
        if self.front_position or self.back_position:
            return self._manage_position(spot, vol)

        # 检查开仓条件
        return self._check_entry(spot, vol, data)

    def _check_entry(
        self,
        spot: float,
        vol: float,
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """检查开仓条件"""

        if self.strategy_type == "calendar_spread":
            return self._calendar_spread_entry(spot, vol, data)
        elif self.strategy_type == "vol_short":
            return self._vol_short_entry(spot, vol, data)

        return {"action": "hold", "reason": "no_signal"}

    def _calendar_spread_entry(
        self,
        spot: float,
        vol: float,
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """日历价差开仓逻辑

        卖出近月期权，买入远月期权
        赚取时间价值衰减差异
        """
        # 简化的开仓逻辑
        front_dte = self.params["front_dte"]
        back_dte = self.params["back_dte"]
        target_delta = self.params["target_delta"]

        # 假设远月波动率高于近月一定阈值时开仓
        # 实际应该比较同一行权价的隐含波动率
        vol_spread = 0.05  # 假设值

        if vol_spread < self.params["vol_spread_threshold"]:
            return {"action": "hold", "reason": "insufficient_vol_spread"}

        # 构建合约
        strike = spot
        front_expiry = datetime.now() + pd.Timedelta(days=front_dte)
        back_expiry = datetime.now() + pd.Timedelta(days=back_dte)

        front_contract = OptionContract(
            symbol=f"{self.underlying}_call_front",
            option_type="call",
            strike=strike,
            expiry=front_expiry,
            underlying=self.underlying
        )

        back_contract = OptionContract(
            symbol=f"{self.underlying}_call_back",
            option_type="call",
            strike=strike,
            expiry=back_expiry,
            underlying=self.underlying
        )

        front_price = self.pricer.price(front_contract, spot, vol)
        back_price = self.pricer.price(back_contract, spot, vol)

        # 记录持仓
        self.front_position = OptionPosition(
            contract=front_contract,
            quantity=-1,  # 卖出近月
            entry_price=front_price,
            entry_date=datetime.now(),
            current_price=front_price
        )

        self.back_position = OptionPosition(
            contract=back_contract,
            quantity=1,   # 买入远月
            entry_price=back_price,
            entry_date=datetime.now(),
            current_price=back_price
        )

        return {
            "action": "open_calendar_spread",
            "reason": "positive_vol_spread",
            "front_price": front_price,
            "back_price": back_price,
            "net_premium": front_price - back_price,
            "note": f"Sell {front_dte}d Call, Buy {back_dte}d Call"
        }

    def _vol_short_entry(
        self,
        spot: float,
        vol: float,
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """做空波动率策略（简化版）"""
        # 当隐含波动率显著高于历史波动率时做空
        # 这里简化处理
        return {"action": "hold", "reason": "not_implemented"}

    def _manage_position(self, spot: float, vol: float) -> Dict[str, Any]:
        """管理现有仓位"""
        total_pnl = self._get_unrealized_pnl()
        entry_value = 0

        if self.front_position:
            entry_value += abs(self.front_position.entry_price * self.front_position.quantity)
        if self.back_position:
            entry_value += abs(self.back_position.entry_price * self.back_position.quantity)

        if entry_value == 0:
            return {"action": "hold", "reason": "monitoring"}

        pnl_pct = total_pnl / entry_value

        # 止盈
        if pnl_pct >= self.params["profit_take"]:
            return self._close_position("profit_take", pnl_pct)

        # 止损
        if pnl_pct <= -self.params["stop_loss"]:
            return self._close_position("stop_loss", pnl_pct)

        # 近月即将到期
        if self.front_position:
            dte = self.front_position.contract.time_to_maturity() * 365
            if dte <= 5:
                return self._close_position("expiry_approaching", pnl_pct)

        return {"action": "hold", "reason": "monitoring"}

    def _close_position(self, reason: str, pnl_pct: float) -> Dict[str, Any]:
        """平仓"""
        realized_pnl = self._get_unrealized_pnl()

        self.front_position = None
        self.back_position = None

        return {
            "action": "close_all",
            "reason": reason,
            "realized_pnl": realized_pnl,
            "pnl_pct": pnl_pct,
            "note": f"Close all positions: {reason}"
        }

    def select_option(self, data: pd.DataFrame) -> Optional[OptionContract]:
        return None

    def should_adjust(self, data: pd.DataFrame) -> bool:
        return True

    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        result = self.on_data(data)
        return result.signals

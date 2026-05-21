from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger


@dataclass
class Trade:
    """交易记录"""
    date: datetime
    symbol: str
    action: str  # BUY, SELL
    shares: int
    price: float
    commission: float
    amount: float


@dataclass
class Position:
    """持仓记录"""
    symbol: str
    shares: int = 0
    avg_cost: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0


class Portfolio:
    """投资组合

    管理现金、持仓和交易
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage = slippage

        self.positions: Dict[str, int] = {}
        self.position_details: Dict[str, Position] = {}
        self.trade_history: List[Trade] = []
        self.total_value = initial_cash

    def update_market_value(self, prices: Dict[str, float], date: datetime):
        """更新持仓市值"""
        position_value = 0.0

        for symbol, shares in self.positions.items():
            if symbol in prices:
                price = prices[symbol]
                market_value = shares * price
                position_value += market_value

                # 更新持仓详情
                if symbol in self.position_details:
                    pos = self.position_details[symbol]
                    pos.market_value = market_value
                    pos.unrealized_pnl = market_value - (pos.avg_cost * shares)

        self.total_value = self.cash + position_value

    def buy(self, symbol: str, shares: int, price: float, date: datetime) -> bool:
        """买入"""
        # 考虑滑点
        executed_price = price * (1 + self.slippage)
        amount = shares * executed_price
        commission = amount * self.commission_rate
        total_cost = amount + commission

        if total_cost > self.cash:
            logger.warning(f"Insufficient cash to buy {shares} shares of {symbol}")
            return False

        # 更新现金
        self.cash -= total_cost

        # 更新持仓
        if symbol in self.positions:
            old_shares = self.positions[symbol]
            old_cost = self.position_details[symbol].avg_cost * old_shares
            new_cost = old_cost + amount
            self.positions[symbol] += shares
            self.position_details[symbol].avg_cost = new_cost / self.positions[symbol]
            self.position_details[symbol].shares = self.positions[symbol]
        else:
            self.positions[symbol] = shares
            self.position_details[symbol] = Position(
                symbol=symbol,
                shares=shares,
                avg_cost=executed_price,
                market_value=amount
            )

        # 记录交易
        trade = Trade(
            date=date,
            symbol=symbol,
            action="BUY",
            shares=shares,
            price=executed_price,
            commission=commission,
            amount=amount
        )
        self.trade_history.append(trade)

        logger.debug(f"BUY {shares} {symbol} @ {executed_price:.2f}")
        return True

    def sell(self, symbol: str, shares: int, price: float, date: datetime) -> bool:
        """卖出"""
        if symbol not in self.positions or self.positions[symbol] < shares:
            logger.warning(f"Insufficient shares to sell {shares} of {symbol}")
            return False

        # 考虑滑点
        executed_price = price * (1 - self.slippage)
        amount = shares * executed_price
        commission = amount * self.commission_rate
        net_amount = amount - commission

        # 更新现金
        self.cash += net_amount

        # 更新持仓
        self.positions[symbol] -= shares
        if self.positions[symbol] == 0:
            del self.positions[symbol]
            del self.position_details[symbol]
        else:
            self.position_details[symbol].shares = self.positions[symbol]

        # 记录交易
        trade = Trade(
            date=date,
            symbol=symbol,
            action="SELL",
            shares=shares,
            price=executed_price,
            commission=commission,
            amount=amount
        )
        self.trade_history.append(trade)

        logger.debug(f"SELL {shares} {symbol} @ {executed_price:.2f}")
        return True

    def rebalance(
        self,
        symbol: str,
        target_weight: float,
        price: float,
        date: datetime
    ):
        """再平衡到目标权重"""
        target_value = self.total_value * target_weight
        current_value = self.positions.get(symbol, 0) * price

        diff_value = target_value - current_value

        if abs(diff_value) < price:  # 变化太小，不调仓
            return

        if diff_value > 0:  # 需要买入
            shares = int(diff_value / (price * (1 + self.slippage)))
            if shares > 0:
                self.buy(symbol, shares, price, date)
        else:  # 需要卖出
            shares = int(abs(diff_value) / (price * (1 - self.slippage)))
            available_shares = self.positions.get(symbol, 0)
            shares = min(shares, available_shares)
            if shares > 0:
                self.sell(symbol, shares, price, date)

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓详情"""
        return self.position_details.get(symbol)

    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self.position_details.values())

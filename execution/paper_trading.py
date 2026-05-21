from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from execution.base import BrokerBase
from backtest.portfolio import Portfolio


class PaperTradingBroker(BrokerBase):
    """模拟交易券商

    用于策略的模拟盘验证，不实际下单
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001
    ):
        super().__init__("PaperTrading")
        self.portfolio = Portfolio(
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            slippage=slippage
        )
        self.orders: Dict[str, Dict] = {}
        self.order_counter = 0

    def connect(self) -> bool:
        """连接（模拟）"""
        self.is_connected = True
        logger.info("PaperTrading connected")
        return True

    def disconnect(self):
        """断开连接"""
        self.is_connected = False
        logger.info("PaperTrading disconnected")

    def buy(
        self,
        symbol: str,
        shares: int,
        price: Optional[float] = None,
        order_type: str = "market"
    ) -> str:
        """模拟买入"""
        self.order_counter += 1
        order_id = f"PAPER_BUY_{self.order_counter}"

        self.orders[order_id] = {
            "symbol": symbol,
            "action": "BUY",
            "shares": shares,
            "price": price,
            "status": "SUBMITTED",
            "time": datetime.now()
        }

        logger.info(f"[PAPER] Buy order submitted: {order_id} {shares} {symbol}")
        return order_id

    def sell(
        self,
        symbol: str,
        shares: int,
        price: Optional[float] = None,
        order_type: str = "market"
    ) -> str:
        """模拟卖出"""
        self.order_counter += 1
        order_id = f"PAPER_SELL_{self.order_counter}"

        self.orders[order_id] = {
            "symbol": symbol,
            "action": "SELL",
            "shares": shares,
            "price": price,
            "status": "SUBMITTED",
            "time": datetime.now()
        }

        logger.info(f"[PAPER] Sell order submitted: {order_id} {shares} {symbol}")
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
            logger.info(f"[PAPER] Order cancelled: {order_id}")
            return True
        return False

    def get_order_status(self, order_id: str) -> Dict:
        """查询订单状态"""
        return self.orders.get(order_id, {})

    def get_positions(self) -> Dict[str, int]:
        """获取持仓"""
        return self.portfolio.positions.copy()

    def get_account(self) -> Dict:
        """获取账户信息"""
        return {
            "cash": self.portfolio.cash,
            "total_value": self.portfolio.total_value,
            "positions": self.portfolio.get_all_positions()
        }

    def update_price(self, prices: Dict[str, float], date: datetime):
        """更新价格（模拟行情驱动）"""
        self.portfolio.update_market_value(prices, date)

    def confirm_order(self, order_id: str, executed_price: float, executed_shares: int):
        """确认订单成交（由外部调用模拟成交）"""
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]
        date = datetime.now()

        if order["action"] == "BUY":
            self.portfolio.buy(
                order["symbol"],
                executed_shares,
                executed_price,
                date
            )
        else:
            self.portfolio.sell(
                order["symbol"],
                executed_shares,
                executed_price,
                date
            )

        order["status"] = "FILLED"
        order["executed_price"] = executed_price
        order["executed_shares"] = executed_shares

        return True

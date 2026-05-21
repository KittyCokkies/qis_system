from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from strategies.base import StrategyResult


class BrokerBase(ABC):
    """券商接口基类

    定义实盘交易所需的接口
    """

    def __init__(self, name: str):
        self.name = name
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """连接交易服务器"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def buy(
        self,
        symbol: str,
        shares: int,
        price: Optional[float] = None,
        order_type: str = "market"
    ) -> str:
        """买入下单

        Args:
            symbol: 标的代码
            shares: 数量
            price: 价格，None表示市价单
            order_type: 订单类型 (market, limit)

        Returns:
            订单ID
        """
        pass

    @abstractmethod
    def sell(
        self,
        symbol: str,
        shares: int,
        price: Optional[float] = None,
        order_type: str = "market"
    ) -> str:
        """卖出下单"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        """查询订单状态"""
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, int]:
        """获取当前持仓"""
        pass

    @abstractmethod
    def get_account(self) -> Dict:
        """获取账户信息

        Returns:
            {
                "cash": 可用现金,
                "total_value": 总资产,
                "positions": 持仓详情
            }
        """
        pass

    def execute_strategy_result(self, result: StrategyResult) -> List[str]:
        """执行策略结果

        根据策略信号执行批量交易
        """
        order_ids = []

        for symbol, signal in result.signals.items():
            if signal.name == "BUY":
                # 计算买入数量（根据权重）
                weight = result.weights.get(symbol, 0)
                # 具体实现需要获取账户信息计算
                pass
            elif signal.name == "SELL":
                # 卖出全部
                pass

        return order_ids

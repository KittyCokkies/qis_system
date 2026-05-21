from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger


class SignalType(Enum):
    """信号类型"""
    BUY = 1
    SELL = -1
    HOLD = 0
    REBALANCE = 2


@dataclass
class StrategyResult:
    """策略结果"""
    timestamp: datetime
    signals: Dict[str, SignalType] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    positions: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_total_weight(self) -> float:
        """获取总权重"""
        return sum(self.weights.values())

    def get_active_positions(self) -> List[str]:
        """获取有持仓的标的"""
        return [k for k, v in self.positions.items() if v != 0]


class StrategyBase(ABC):
    """策略基类

    所有策略（资产配置、CTA、多因子等）都继承自此基类
    """

    def __init__(
        self,
        name: str,
        symbols: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.symbols = symbols
        self.params = params or {}
        self.is_initialized = False
        self.current_result: Optional[StrategyResult] = None
        self.history: List[StrategyResult] = []
        logger.info(f"Strategy '{name}' initialized with {len(symbols)} symbols")

    @abstractmethod
    def initialize(self) -> "StrategyBase":
        """初始化策略

        在策略开始运行前调用，用于加载历史数据、初始化模型等
        """
        pass

    @abstractmethod
    def on_data(self, data: pd.DataFrame) -> StrategyResult:
        """处理新数据

        Args:
            data: 最新市场数据

        Returns:
            策略结果
        """
        pass

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> Dict[str, SignalType]:
        """生成交易信号

        Args:
            data: 市场数据

        Returns:
            标的->信号的字典
        """
        pass

    def set_params(self, **params) -> "StrategyBase":
        """设置策略参数"""
        self.params.update(params)
        logger.debug(f"Strategy '{self.name}' params updated: {params}")
        return self

    def get_params(self) -> Dict[str, Any]:
        """获取策略参数"""
        return self.params.copy()

    def update_result(self, result: StrategyResult):
        """更新策略结果"""
        self.current_result = result
        self.history.append(result)

    def get_history(self, n: Optional[int] = None) -> List[StrategyResult]:
        """获取历史结果

        Args:
            n: 最近n条，None表示全部
        """
        if n is None:
            return self.history.copy()
        return self.history[-n:]

    def reset(self):
        """重置策略状态"""
        self.current_result = None
        self.history = []
        self.is_initialized = False
        logger.info(f"Strategy '{self.name}' reset")

    def validate_data(self, data: pd.DataFrame) -> bool:
        """验证数据是否有效"""
        if data.empty:
            logger.warning("Empty data received")
            return False
        return True

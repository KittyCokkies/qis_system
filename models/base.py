from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from loguru import logger


class ModelBase(ABC):
    """模型基类

    所有模型（资产配置、因子、CTA等）都继承自此基类
    """

    def __init__(self, name: str, params: Optional[Dict[str, Any]] = None):
        self.name = name
        self.params = params or {}
        self.is_fitted = False
        self.metadata: Dict[str, Any] = {}
        logger.info(f"Model '{name}' initialized")

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> "ModelBase":
        """训练模型

        Args:
            data: 训练数据

        Returns:
            self (链式调用)
        """
        pass

    @abstractmethod
    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        """预测/生成信号

        Args:
            data: 输入数据

        Returns:
            预测结果DataFrame
        """
        pass

    def get_params(self) -> Dict[str, Any]:
        """获取模型参数"""
        return self.params.copy()

    def set_params(self, **params) -> "ModelBase":
        """设置模型参数"""
        self.params.update(params)
        logger.debug(f"Model '{self.name}' params updated: {params}")
        return self

    def get_metadata(self) -> Dict[str, Any]:
        """获取模型元数据"""
        return self.metadata.copy()


class AllocationModelBase(ModelBase):
    """资产配置模型基类

    用于大类资产配置策略，如Risk Parity、Black-Litterman等
    """

    def __init__(self, name: str, assets: List[str], params: Optional[Dict[str, Any]] = None):
        super().__init__(name, params)
        self.assets = assets
        self.weights: Optional[np.ndarray] = None
        self.cov_matrix: Optional[np.ndarray] = None

    @abstractmethod
    def optimize(self, returns: pd.DataFrame) -> np.ndarray:
        """优化组合权重

        Args:
            returns: 资产收益率DataFrame

        Returns:
            最优权重数组
        """
        pass

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        """资产配置模型的predict返回权重"""
        weights = self.optimize(data)
        return pd.DataFrame(
            [weights],
            columns=self.assets,
            index=[data.index[-1]] if len(data.index) > 0 else [pd.Timestamp.now()]
        )

    def get_weights(self) -> Optional[pd.DataFrame]:
        """获取最新权重"""
        if self.weights is None:
            return None
        return pd.DataFrame(
            [self.weights],
            columns=self.assets
        )

    def calculate_portfolio_return(
        self,
        returns: pd.DataFrame,
        weights: Optional[np.ndarray] = None
    ) -> pd.Series:
        """计算组合收益率

        Args:
            returns: 资产收益率
            weights: 权重，None则使用优化后的权重

        Returns:
            组合收益率序列
        """
        w = weights if weights is not None else self.weights
        if w is None:
            raise ValueError("Weights not set, please run optimize() first")
        return returns.dot(w)


class FactorModelBase(ModelBase):
    """多因子模型基类

    用于多因子选股策略
    """

    def __init__(
        self,
        name: str,
        factors: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        super().__init__(name, params)
        self.factors = factors
        self.factor_weights: Optional[Dict[str, float]] = None

    @abstractmethod
    def calculate_factors(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算因子值

        Args:
            data: 原始数据

        Returns:
            因子值DataFrame
        """
        pass

    @abstractmethod
    def score_stocks(self, factor_data: pd.DataFrame) -> pd.DataFrame:
        """股票打分

        Args:
            factor_data: 因子数据

        Returns:
            带有score列的DataFrame
        """
        pass

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        """预测返回股票打分"""
        factor_data = self.calculate_factors(data)
        return self.score_stocks(factor_data)

    def select_stocks(
        self,
        scores: pd.DataFrame,
        n: int = 50,
        asc: bool = False
    ) -> List[str]:
        """根据分数选股

        Args:
            scores: 包含score列的DataFrame
            n: 选择的股票数量
            asc: 是否升序（True=选择分数最低的）

        Returns:
            选中的股票代码列表
        """
        sorted_scores = scores.sort_values("score", ascending=asc)
        return sorted_scores.index[:n].tolist()


class CTAModelBase(ModelBase):
    """CTA信号模型基类

    用于CTA策略，生成多空信号
    """

    SIGNAL_BUY = 1
    SIGNAL_SELL = -1
    SIGNAL_HOLD = 0

    def __init__(self, name: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(name, params)
        self.position: int = 0
        self.signals: List[int] = []

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> int:
        """生成交易信号

        Args:
            data: 价格数据

        Returns:
            信号: 1=买入, -1=卖出, 0=持有
        """
        pass

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        """预测返回交易信号"""
        signal = self.generate_signal(data)
        return pd.DataFrame(
            {"signal": [signal]},
            index=[data.index[-1]] if len(data.index) > 0 else [pd.Timestamp.now()]
        )

    def get_position_size(self, signal: int, current_position: int) -> int:
        """计算仓位

        Args:
            signal: 交易信号
            current_position: 当前仓位

        Returns:
            目标仓位
        """
        return signal

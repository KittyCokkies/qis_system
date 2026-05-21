from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from loguru import logger

from models.factor.factor_def import FactorDefinitions, FactorType


class FactorCalculator:
    """因子计算器

    负责从原始数据计算各类因子值
    """

    def __init__(self):
        self.factor_defs = FactorDefinitions()
        self.factor_data: Dict[str, pd.DataFrame] = {}

    def calculate_technical_factors(
        self,
        price_data: pd.DataFrame,
        windows: List[int] = [5, 10, 20, 60]
    ) -> pd.DataFrame:
        """计算技术面因子

        Args:
            price_data: 价格数据，包含 [open, high, low, close, volume]
            windows: 计算窗口

        Returns:
            因子值DataFrame
        """
        factors = pd.DataFrame(index=price_data.index)

        close = price_data["close"]
        volume = price_data["volume"]
        returns = close.pct_change()

        # 动量因子
        for w in windows:
            factors[f"momentum_{w}d"] = close.pct_change(w)
            factors[f"volatility_{w}d"] = returns.rolling(w).std() * np.sqrt(252)

        # RSI
        factors["rsi_14d"] = self.factor_defs.rsi(close, 14)

        # 移动平均线距离
        for w in windows:
            ma = close.rolling(w).mean()
            factors[f"ma_dist_{w}d"] = (close - ma) / ma

        # 成交量因子
        factors["turnover_ratio"] = volume / volume.rolling(20).mean()

        # 波动率相关
        factors["max_drawdown_20d"] = self.factor_defs.max_drawdown(close, 20)

        return factors

    def calculate_fundamental_factors(
        self,
        financial_data: pd.DataFrame
    ) -> pd.DataFrame:
        """计算基本面因子

        Args:
            financial_data: 财务数据，包含必要的财务字段

        Returns:
            因子值DataFrame
        """
        factors = pd.DataFrame(index=financial_data.index)

        # 价值因子
        if all(col in financial_data.columns for col in ["close", "eps"]):
            factors["pe_ratio"] = self.factor_defs.pe_ratio(
                financial_data["close"], financial_data["eps"]
            )

        if all(col in financial_data.columns for col in ["close", "bps"]):
            factors["pb_ratio"] = self.factor_defs.pb_ratio(
                financial_data["close"], financial_data["bps"]
            )

        # 盈利能力因子
        if all(col in financial_data.columns for col in ["net_income", "equity"]):
            factors["roe"] = self.factor_defs.roe(
                financial_data["net_income"], financial_data["equity"]
            )

        if all(col in financial_data.columns for col in ["net_income", "total_assets"]):
            factors["roa"] = self.factor_defs.roa(
                financial_data["net_income"], financial_data["total_assets"]
            )

        if all(col in financial_data.columns for col in ["gross_profit", "revenue"]):
            factors["gross_margin"] = self.factor_defs.gross_margin(
                financial_data["gross_profit"], financial_data["revenue"]
            )

        # 杠杆因子
        if all(col in financial_data.columns for col in ["total_debt", "equity"]):
            factors["debt_to_equity"] = self.factor_defs.debt_to_equity(
                financial_data["total_debt"], financial_data["equity"]
            )

        return factors

    def cross_sectional_rank(
        self,
        factor_data: pd.DataFrame,
        factor_cols: List[str],
        directions: Optional[Dict[str, int]] = None
    ) -> pd.DataFrame:
        """截面排序标准化

        Args:
            factor_data: 因子数据
            factor_cols: 需要排序的因子列
            directions: 因子方向，1=越大越好，-1=越小越好

        Returns:
            排序后的因子值 (0-1之间)
        """
        if directions is None:
            directions = {f: 1 for f in factor_cols}

        ranked_data = factor_data.copy()

        for col in factor_cols:
            if col not in factor_data.columns:
                continue

            direction = directions.get(col, 1)
            # 排名并归一化到 [0, 1]
            ranks = factor_data[col].rank(pct=True, na_option="keep")
            ranked_data[f"{col}_rank"] = ranks if direction == 1 else (1 - ranks)

        return ranked_data

    def combine_factors(
        self,
        factor_data: pd.DataFrame,
        weights: Optional[Dict[str, float]] = None,
        method: str = "weighted_sum"
    ) -> pd.Series:
        """合成多因子得分

        Args:
            factor_data: 包含因子排名列的数据
            weights: 各因子权重，None则等权
            method: 合成方法 ("weighted_sum", "equal", "ic_weighted")

        Returns:
            合成得分Series
        """
        rank_cols = [c for c in factor_data.columns if c.endswith("_rank")]

        if not rank_cols:
            logger.warning("No rank columns found in factor data")
            return pd.Series(index=factor_data.index)

        if weights is None:
            weights = {c: 1.0 / len(rank_cols) for c in rank_cols}

        if method == "weighted_sum":
            score = pd.Series(0.0, index=factor_data.index)
            for col in rank_cols:
                if col in weights:
                    score += factor_data[col].fillna(0.5) * weights[col]
        elif method == "equal":
            score = factor_data[rank_cols].mean(axis=1)
        else:
            raise ValueError(f"Unknown combination method: {method}")

        return score

    def neutralize(
        self,
        factor_series: pd.Series,
        group: pd.Series,
        method: str = "median"
    ) -> pd.Series:
        """因子中性化（行业/市值）

        Args:
            factor_series: 原始因子值
            group: 分组（如行业分类）
            method: 中性化方法 ("mean", "median")

        Returns:
            中性化后的因子值
        """
        neutralized = factor_series.copy()

        for g in group.unique():
            mask = group == g
            if method == "mean":
                neutralized[mask] = factor_series[mask] - factor_series[mask].mean()
            elif method == "median":
                neutralized[mask] = factor_series[mask] - factor_series[mask].median()

        return neutralized

    def winsorize(
        self,
        factor_series: pd.Series,
        lower: float = 0.01,
        upper: float = 0.99
    ) -> pd.Series:
        """去极值处理（缩尾）

        Args:
            factor_series: 原始因子值
            lower: 下分位数
            upper: 上分位数

        Returns:
            去极值后的因子值
        """
        lower_bound = factor_series.quantile(lower)
        upper_bound = factor_series.quantile(upper)
        return factor_series.clip(lower_bound, upper_bound)

    def standardize(self, factor_series: pd.Series) -> pd.Series:
        """标准化（z-score）"""
        return (factor_series - factor_series.mean()) / factor_series.std()

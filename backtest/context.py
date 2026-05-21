from datetime import datetime
from typing import Any, Dict, List

import pandas as pd


class BacktestContext:
    """回测上下文

    记录回测过程中的状态变化
    """

    def __init__(self, initial_cash: float, start_date: datetime):
        self.initial_cash = initial_cash
        self.start_date = start_date
        self.current_date = start_date
        self.current_cash = initial_cash
        self.current_positions: Dict[str, int] = {}
        self.current_value = initial_cash

        # 历史记录
        self.history: List[Dict[str, Any]] = []

    def update(
        self,
        date: datetime,
        portfolio_value: float,
        positions: Dict[str, int],
        cash: float
    ):
        """更新状态"""
        self.current_date = date
        self.current_value = portfolio_value
        self.current_positions = positions.copy()
        self.current_cash = cash

        self.history.append({
            "date": date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "positions": positions.copy()
        })

    def get_equity_curve(self) -> pd.Series:
        """获取权益曲线"""
        if not self.history:
            return pd.Series()

        df = pd.DataFrame(self.history)
        df.set_index("date", inplace=True)
        return df["portfolio_value"]

    def get_positions_history(self) -> pd.DataFrame:
        """获取持仓历史"""
        if not self.history:
            return pd.DataFrame()

        records = []
        for record in self.history:
            for symbol, shares in record["positions"].items():
                records.append({
                    "date": record["date"],
                    "symbol": symbol,
                    "shares": shares
                })

        return pd.DataFrame(records)

    def get_current_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "date": self.current_date,
            "cash": self.current_cash,
            "positions": self.current_positions.copy(),
            "total_value": self.current_value
        }

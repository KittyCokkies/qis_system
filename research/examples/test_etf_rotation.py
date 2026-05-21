"""
ETF轮动策略示例

演示如何进行ETF轮动配置
"""

import numpy as np
import pandas as pd
from loguru import logger

from strategies import ETFRotationStrategy
from backtest import BacktestEngine


def generate_sample_etf_data(etfs: list, n_days: int = 200) -> pd.DataFrame:
    """生成ETF示例数据"""
    np.random.seed(123)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_days, freq='B')

    data = pd.DataFrame(index=dates)

    for etf in etfs:
        # 添加趋势性
        trend = np.sin(np.linspace(0, 4*np.pi, n_days)) * 0.1 + 0.0002
        returns = np.random.normal(trend, 0.015)
        data[etf] = (1 + returns).cumprod() * 100

    return data


def main():
    from utils import setup_logger
    setup_logger()

    logger.info("开始ETF轮动策略回测示例")

    # 定义ETF池
    etfs = [
        "沪深300ETF",
        "中证500ETF",
        "创业板ETF",
        "券商ETF",
        "医药ETF",
        "科技ETF",
        "消费ETF",
        "红利ETF"
    ]

    # 生成示例数据
    data = generate_sample_etf_data(etfs, n_days=150)
    logger.info(f"生成ETF数据: {data.shape}")

    # 创建ETF轮动策略
    strategy = ETFRotationStrategy(
        name="ETF_Momentum_Rotation",
        etfs=etfs,
        params={
            "lookback_days": 20,
            "momentum_window": 60,
            "n_holdings": 3,
            "rebalance_freq": "W",
            "score_method": "risk_adj_momentum",
            "momentum_threshold": 0
        }
    )

    # 运行回测
    engine = BacktestEngine(
        initial_cash=1_000_000,
        commission_rate=0.0003,
        slippage=0.001
    )

    result = engine.run(strategy, data)

    # 输出结果
    print(result.summary())

    # 查看持仓变化
    if not result.positions.empty:
        print("\n最后5期持仓:")
        print(result.positions.tail(10))


if __name__ == "__main__":
    main()
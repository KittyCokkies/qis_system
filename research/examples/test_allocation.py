"""
资产配置策略示例

演示如何使用风险平价模型进行资产配置
"""

import numpy as np
import pandas as pd
from loguru import logger

from models.allocation import RiskParityModel, MeanVarianceModel
from strategies import AllocationStrategy
from backtest import BacktestEngine


def generate_sample_data(assets: list, n_days: int = 500) -> pd.DataFrame:
    """生成示例数据"""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_days, freq='B')

    # 生成相关收益率
    returns = np.random.multivariate_normal(
        mean=[0.0003] * len(assets),
        cov=np.diag([0.02] * len(assets)) + 0.0001,
        size=n_days
    )

    # 生成价格
    prices = pd.DataFrame(
        (1 + returns).cumprod() * 100,
        columns=assets,
        index=dates
    )

    return prices


def main():
    # 配置日志
    from utils import setup_logger
    setup_logger()

    logger.info("开始资产配置策略回测示例")

    # 定义资产
    assets = ["000300.SH", "000905.SH", "黄金ETF", "债券ETF", "纳指ETF"]

    # 生成示例数据
    data = generate_sample_data(assets, n_days=252)
    logger.info(f"生成示例数据: {data.shape}")

    # 创建风险平价策略
    strategy = AllocationStrategy(
        name="RiskParity_Allocation",
        symbols=assets,
        model_type="risk_parity",
        rebalance_freq="M",
        lookback_days=60,
        params={"max_weight": 0.4}
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

    # 对比：均值方差优化
    logger.info("\n对比：均值方差优化策略")
    strategy_mv = AllocationStrategy(
        name="MeanVariance_Allocation",
        symbols=assets,
        model_type="mean_variance",
        rebalance_freq="M",
        lookback_days=60,
        params={
            "objective": "sharpe",
            "max_weight": 0.5,
            "risk_free_rate": 0.02
        }
    )

    result_mv = engine.run(strategy_mv, data)
    print(result_mv.summary())


if __name__ == "__main__":
    main()
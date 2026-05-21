"""
期权策略示例

演示备兑开仓(Covered Call)和波动率套利(Vol Carry)策略
"""

import numpy as np
import pandas as pd
from datetime import datetime
from loguru import logger

from strategies import CoveredCallStrategy, VolCarryStrategy
from models.option.pricing import BlackScholesModel, OptionContract
from models.option.greeks import GreeksCalculator
from utils import setup_logger


def test_black_scholes():
    """测试Black-Scholes定价模型"""
    logger.info("=" * 60)
    logger.info("测试 Black-Scholes 期权定价模型")
    logger.info("=" * 60)

    # 参数
    spot = 5.0          # 标的价格（ETF）
    strike = 5.2        # 行权价（虚值约4%）
    time = 30 / 365     # 30天到期
    rate = 0.03         # 无风险利率3%
    vol = 0.25          # 波动率25%

    # 计算看涨期权价格
    call_price = BlackScholesModel.price("call", spot, strike, time, rate, vol)
    put_price = BlackScholesModel.price("put", spot, strike, time, rate, vol)

    logger.info(f"标的价格: {spot}")
    logger.info(f"行权价: {strike}")
    logger.info(f"到期时间: {time:.4f} 年 ({time*365:.0f}天)")
    logger.info(f"波动率: {vol:.1%}")
    logger.info(f"看涨期权价格: {call_price:.4f}")
    logger.info(f"看跌期权价格: {put_price:.4f}")

    # 计算希腊值
    calc = GreeksCalculator(rate)
    contract = OptionContract(
        symbol="510300_call",
        option_type="call",
        strike=strike,
        expiry=datetime.now(),
        underlying="510300.SH"
    )

    greeks = calc.calculate(contract, spot, vol)
    logger.info(f"\n希腊值:")
    logger.info(f"  Delta: {greeks.delta:.4f}")
    logger.info(f"  Gamma: {greeks.gamma:.4f}")
    logger.info(f"  Vega:  {greeks.vega:.4f}")
    logger.info(f"  Theta: {greeks.theta:.4f}")
    logger.info(f"  Rho:   {greeks.rho:.4f}")

    return call_price


def test_covered_call():
    """测试备兑开仓策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 备兑开仓策略 (Covered Call)")
    logger.info("=" * 60)

    # 生成模拟价格数据
    np.random.seed(42)
    n_days = 60
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    # 生成带有趋势的价格序列
    trend = np.cumsum(np.random.randn(n_days) * 0.01)
    prices = 5.0 * (1 + trend)

    data = pd.DataFrame({
        "510300.SH": prices
    }, index=dates)

    logger.info(f"生成 {len(data)} 天的模拟数据")
    logger.info(f"价格范围: {prices.min():.2f} - {prices.max():.2f}")

    # 创建备兑策略
    strategy = CoveredCallStrategy(
        name="CoveredCall_510300",
        underlying="510300.SH",
        params={
            "target_delta": 0.3,
            "dte_target": 30,
            "dte_min": 7,
            "profit_take_pct": 0.5,
            "lot_size": 10000,
        }
    )

    # 模拟运行
    logger.info("\n策略运行日志:")
    for i in range(30, len(data), 5):  # 每5天运行一次
        current_data = data.iloc[:i]
        result = strategy.on_data(current_data)

        if result.metadata.get("action") not in ["hold", None]:
            logger.info(f"日期: {result.timestamp.strftime('%Y-%m-%d')}")
            logger.info(f"  动作: {result.metadata.get('action')}")
            logger.info(f"  原因: {result.metadata.get('reason')}")
            logger.info(f"  标的价格: {result.metadata.get('current_price', 0):.3f}")

            if "premium_received" in result.metadata:
                logger.info(f"  收取权利金: {result.metadata['premium_received']:.2f}")

            if "portfolio_greeks" in result.metadata and result.metadata["portfolio_greeks"]:
                greeks = result.metadata["portfolio_greeks"]
                logger.info(f"  组合Delta: {greeks.get('delta', 0):.4f}")
                logger.info(f"  组合Theta: {greeks.get('theta', 0):.4f}")

    # 计算收益增强效果
    current_price = data["510300.SH"].iloc[-1]
    enhancement = strategy.calculate_yield_enhancement(current_price)

    logger.info("\n收益增强分析:")
    logger.info(f"  月度收益率: {enhancement['monthly_yield']:.2%}")
    logger.info(f"  年化收益率: {enhancement['annual_yield']:.2%}")
    logger.info(f"  权利金金额: {enhancement['premium_amount']:.2f}")


def test_vol_carry():
    """测试波动率套利策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 波动率套利策略 (Vol Carry - Calendar Spread)")
    logger.info("=" * 60)

    # 生成模拟数据
    np.random.seed(123)
    n_days = 100
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

    # 生成不同波动率环境的价格
    prices = 5.0 * np.exp(np.cumsum(np.random.randn(n_days) * 0.015))

    data = pd.DataFrame({
        "510050.SH": prices
    }, index=dates)

    logger.info(f"生成 {len(data)} 天的模拟数据")

    # 创建波动率套利策略
    strategy = VolCarryStrategy(
        name="VolCarry_510050",
        underlying="510050.SH",
        params={
            "strategy_type": "calendar_spread",
            "front_dte": 30,
            "back_dte": 60,
            "target_delta": 0.3,
            "vol_spread_threshold": 0.02,
            "profit_take": 0.5,
            "stop_loss": 2.0,
        }
    )

    # 模拟运行
    logger.info("\n策略运行日志:")
    for i in range(40, len(data), 7):  # 每周运行一次
        current_data = data.iloc[:i]
        result = strategy.on_data(current_data)

        if result.metadata.get("action") not in ["hold", None]:
            logger.info(f"日期: {result.timestamp.strftime('%Y-%m-%d')}")
            logger.info(f"  动作: {result.metadata.get('action')}")
            logger.info(f"  原因: {result.metadata.get('reason')}")
            logger.info(f"  净Theta: {result.metadata.get('net_theta', 0):.4f}")
            logger.info(f"  净Vega: {result.metadata.get('net_vega', 0):.4f}")

            if "front_price" in result.metadata:
                logger.info(f"  近月期权价格: {result.metadata['front_price']:.4f}")
                logger.info(f"  远月期权价格: {result.metadata['back_price']:.4f}")
                logger.info(f"  净权利金: {result.metadata['net_premium']:.4f}")

            if "realized_pnl" in result.metadata:
                logger.info(f"  实现盈亏: {result.metadata['realized_pnl']:.2f}")
                logger.info(f"  盈亏比例: {result.metadata.get('pnl_pct', 0):.2%}")


def test_volatility_analysis():
    """测试波动率分析工具"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 波动率分析")
    logger.info("=" * 60)

    from models.option.volatility import VolatilityCalculator, VolatilityCarryCalculator

    # 生成价格数据
    np.random.seed(456)
    n_days = 252
    returns = np.random.randn(n_days) * 0.02
    prices = pd.Series(100 * np.exp(np.cumsum(returns)))

    # 计算历史波动率
    vol_calc = VolatilityCalculator()

    hv_20 = vol_calc.historical_volatility(prices, window=20)
    hv_60 = vol_calc.historical_volatility(prices, window=60)

    logger.info(f"20日历史波动率: {hv_20:.2%}")
    logger.info(f"60日历史波动率: {hv_60:.2%}")

    # 波动率锥分析
    returns_series = pd.Series(returns)
    carry_calc = VolatilityCarryCalculator()

    vol_cone = carry_calc.vol_cone_analysis(returns_series)
    logger.info("\n波动率锥分析:")
    logger.info(vol_cone.to_string(index=False))

    # 预期波动率溢价
    implied_vol = 0.28  # 假设隐含波动率28%
    premium_analysis = carry_calc.expected_volatility_premium(
        implied_vol, returns_series, lookback_days=252
    )

    logger.info(f"\n波动率溢价分析:")
    logger.info(f"  隐含波动率: {premium_analysis['implied_vol']:.2%}")
    logger.info(f"  平均实现波动率: {premium_analysis['avg_realized_vol']:.2%}")
    logger.info(f"  波动率溢价: {premium_analysis['vol_premium']:.2%}")
    logger.info(f"  交易信号: {premium_analysis['trade_signal']}")


def main():
    """主函数"""
    setup_logger()

    logger.info("\n" + "=" * 70)
    logger.info("QIS System 期权策略示例")
    logger.info("=" * 70)

    # 1. 测试BS模型
    test_black_scholes()

    # 2. 测试备兑策略
    test_covered_call()

    # 3. 测试波动率套利
    test_vol_carry()

    # 4. 测试波动率分析
    test_volatility_analysis()

    logger.info("\n" + "=" * 70)
    logger.info("期权策略示例完成")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

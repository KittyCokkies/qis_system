

# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例1：动态主力合约换月（基于持仓量）
    print("=" * 60)
    print("示例1：动态主力合约换月")
    print("=" * 60)

    analyzer = FutureRolloverAnalyzer()

    # 计算IF股指期货的展期收益（持仓量最大作为主力）
    df_dynamic = analyzer.calculate_rollover_return(
        underlying="IF",
        start_date="2024-01-01",
        end_date="2024-12-31",
        signal_type=RolloverSignalType.OPEN_INTEREST
    )
    print(f"动态换月数据：{len(df_dynamic)} 天")
    if not df_dynamic.empty:
        print(df_dynamic.head(10)[['date', 'main_contract', 'next_contract', 'rollover_return']])

    # 示例2：固定日历换月（推荐用于简单策略）
    print("\n" + "=" * 60)
    print("示例2：固定日历换月（到期前5天自动换月）")
    print("=" * 60)

    df_static = analyzer.calculate_static_rollover(
        underlying="IF",
        start_date="2024-01-01",
        end_date="2024-12-31",
        roll_days_before_expiry=5  # 到期前5天换月
    )
    print(f"固定换月数据：{len(df_static)} 天")
    if not df_static.empty:
        print(df_static.head(10)[['date', 'current_contract', 'next_contract', 'is_rollover_day']])

        # 显示换月日期
        rollover_days = df_static[df_static['is_rollover_day']]
        print(f"\n换月日期（共{len(rollover_days)}次）：")
        print(rollover_days[['date', 'current_contract', 'next_contract', 'rollover_return']])

    # 示例3：获取连续合约价格（已消除换月跳空）
    print("\n" + "=" * 60)
    print("示例3：连续合约价格")
    print("=" * 60)

    if not df_static.empty:
        print(df_static[['date', 'current_contract', 'current_price', 'continuous_price']].head(20))
        print("\n换月跳空消除示例：")
        print(df_static[df_static['is_rollover_day']][['date', 'current_price', 'continuous_price', 'rollover_return']])

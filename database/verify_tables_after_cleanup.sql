-- ========================================================-- 清理后验证脚本-- ========================================================

-- 查看剩余的表（应该是QIS业务表）
SELECT
    tablename,
    CASE
        WHEN tablename IN (
            'assets', 'trade_calendar', 'prices_stock', 'prices_future',
            'prices_future_continuous', 'prices_etf', 'prices_index',
            'factors_asset', 'factors_commodity', 'fx_rates', 'macro_indicators',
            'market_regime', 'strategies', 'strategy_nav', 'target_positions',
            'actual_positions', 'trades', 'roll_executions', 'index_components',
            'industry_classification', 'hedge_instrument_mapping',
            'synthetic_index_series', 'strategy_index_series', 'hedge_comparison',
            'strategy_hedge_config'
        ) THEN '✓ QIS业务表'
        ELSE '? 未知表'
    END as category
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY
    CASE
        WHEN tablename IN (
            'assets', 'trade_calendar', 'prices_stock', 'prices_future',
            'prices_future_continuous', 'prices_etf', 'prices_index',
            'factors_asset', 'factors_commodity', 'fx_rates', 'macro_indicators',
            'market_regime', 'strategies', 'strategy_nav', 'target_positions',
            'actual_positions', 'trades', 'roll_executions', 'index_components',
            'industry_classification', 'hedge_instrument_mapping',
            'synthetic_index_series', 'strategy_index_series', 'hedge_comparison',
            'strategy_hedge_config'
        ) THEN 1
        ELSE 2
    END,
    tablename;

-- 统计表数量
SELECT
    COUNT(*) as total_tables,
    SUM(CASE WHEN tablename IN (
        'assets', 'trade_calendar', 'prices_stock', 'prices_future',
        'prices_future_continuous', 'prices_etf', 'prices_index',
        'factors_asset', 'factors_commodity', 'fx_rates', 'macro_indicators',
        'market_regime', 'strategies', 'strategy_nav', 'target_positions',
        'actual_positions', 'trades', 'roll_executions', 'index_components',
        'industry_classification', 'hedge_instrument_mapping',
        'synthetic_index_series', 'strategy_index_series', 'hedge_comparison',
        'strategy_hedge_config'
    ) THEN 1 ELSE 0 END) as qis_tables
FROM pg_tables
WHERE schemaname = 'public';

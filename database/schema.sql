-- ========================================================
-- QIS System - 本地数据库表结构设计
-- 支持：股票、期货、ETF、指数等多资产类型
-- 支持：多策略管理、回测、实盘跟踪
-- ========================================================

-- --------------------------------------------------------
-- 1. 基础数据表
-- --------------------------------------------------------

-- 资产主表（统一管理的标的列表）
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL UNIQUE,           -- 标的代码，如 "IF2401"、"000001.SZ"
    underlying VARCHAR(10) NOT NULL,              -- 底层品种，如 "IF"、"000001"
    name VARCHAR(100),                            -- 标的名称
    asset_class VARCHAR(20) NOT NULL,             -- 资产类别：stock/future/index/etf/bond/option
    exchange VARCHAR(10),                         -- 交易所：SSE/SZSE/CFFEX/SHFE/DCE/CZCE/INE
    currency VARCHAR(3) DEFAULT 'CNY',            -- 币种
    contract_month VARCHAR(6),                    -- 合约月份（期货/期权），如 "2401"
    list_date DATE,                               -- 上市日期
    delist_date DATE,                             -- 退市/到期日期
    multiplier DECIMAL(10, 4),                    -- 合约乘数（期货用）
    tick_size DECIMAL(10, 4),                     -- 最小变动单位
    is_active BOOLEAN DEFAULT TRUE,               -- 是否可交易
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_asset_class CHECK (asset_class IN ('stock', 'future', 'index', 'etf', 'bond', 'option', 'commodity', 'fund'))
);

CREATE INDEX idx_assets_underlying ON assets(underlying);
CREATE INDEX idx_assets_class ON assets(asset_class);
CREATE INDEX idx_assets_active ON assets(is_active);

-- 交易日历表
CREATE TABLE IF NOT EXISTS trade_calendar (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market VARCHAR(10) NOT NULL,                  -- SSE/SZSE/CFFEX等
    is_trading_day BOOLEAN NOT NULL,              -- 是否交易日
    is_weekend BOOLEAN,                           -- 是否周末
    is_holiday BOOLEAN,                           -- 是否假日
    holiday_name VARCHAR(50),                     -- 假日名称
    UNIQUE(date, market)
);

CREATE INDEX idx_calendar_date ON trade_calendar(date);
CREATE INDEX idx_calendar_market ON trade_calendar(market, is_trading_day);

-- --------------------------------------------------------
-- 2. 价格数据表（按资产类型分表，优化查询性能）
-- --------------------------------------------------------

-- 股票价格表（ETF、个股）- 前复权
CREATE TABLE IF NOT EXISTS prices_stock (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,                  -- 标的代码
    date DATE NOT NULL,                           -- 交易日期
    open DECIMAL(12, 4),                          -- 开盘价（前复权）
    high DECIMAL(12, 4),                          -- 最高价（前复权）
    low DECIMAL(12, 4),                           -- 最低价（前复权）
    close DECIMAL(12, 4),                         -- 收盘价（前复权）
    volume BIGINT,                                -- 成交量（股）
    amount DECIMAL(20, 4),                        -- 成交金额
    adj_factor DECIMAL(10, 6),                    -- 复权因子
    is_st BOOLEAN DEFAULT FALSE,                  -- 是否ST
    is_limit_up BOOLEAN DEFAULT FALSE,            -- 是否涨停
    is_limit_down BOOLEAN DEFAULT FALSE,          -- 是否跌停
    UNIQUE(symbol, date),
    FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_prices_stock_symbol_date ON prices_stock(symbol, date DESC);
CREATE INDEX idx_prices_stock_date ON prices_stock(date);

-- 为已存在的表添加 update_time 字段（如果尚不存在）
ALTER TABLE prices_stock ADD COLUMN IF NOT EXISTS update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 期货价格表（原始合约数据）
CREATE TABLE IF NOT EXISTS prices_future (
    symbol VARCHAR(20) NOT NULL,                  -- 合约代码，如 "IF2401"
    underlying VARCHAR(10) NOT NULL,              -- 品种代码，如 "IF"
    date DATE NOT NULL,                           -- 交易日期
    open DECIMAL(12, 4),                          -- 开盘价
    high DECIMAL(12, 4),                          -- 最高价
    low DECIMAL(12, 4),                           -- 最低价
    close DECIMAL(12, 4),                         -- 收盘价
    settle DECIMAL(12, 4),                        -- 结算价
    volume BIGINT,                                -- 成交量
    amount DECIMAL(20, 4),                        -- 成交金额
    open_interest BIGINT,                         -- 持仓量
    basis DECIMAL(12, 4),                         -- 基差
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 数据写入时间
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_prices_future_symbol_date ON prices_future(symbol, date DESC);
CREATE INDEX idx_prices_future_underlying ON prices_future(underlying, date DESC);
CREATE INDEX idx_prices_future_date ON prices_future(date);

-- 期货连续合约表（展期后的连续价格序列）
CREATE TABLE IF NOT EXISTS prices_future_continuous (
    id BIGSERIAL PRIMARY KEY,
    underlying VARCHAR(10) NOT NULL,              -- 品种代码，如 "IF"
    date DATE NOT NULL,                           -- 交易日期
    current_contract VARCHAR(20),                 -- 当前持有合约
    next_contract VARCHAR(20),                    -- 下月合约
    current_price DECIMAL(12, 4),                 -- 当前合约价格
    next_price DECIMAL(12, 4),                    -- 下月合约价格
    continuous_price DECIMAL(12, 4),              -- 连续合约价格（跳空调整）
    price_diff DECIMAL(12, 4),                    -- 远近月价差
    roll_return DECIMAL(10, 6),                   -- 展期收益
    days_to_expiry INTEGER,                       -- 距离到期天数
    is_roll_day BOOLEAN DEFAULT FALSE,            -- 是否换仓日
    roll_type VARCHAR(20),                        -- 换仓类型：hold/observation_roll/forced_roll
    roll_start_days INTEGER DEFAULT 10,           -- 观察窗口p
    roll_end_days INTEGER DEFAULT 3,              -- 强制窗口q
    open_interest BIGINT,                         -- 持仓量
    volume BIGINT,                                -- 成交量
    UNIQUE(underlying, date, roll_start_days, roll_end_days),
    FOREIGN KEY (current_contract) REFERENCES assets(symbol) ON DELETE SET NULL
);

CREATE INDEX idx_prices_fut_cont_underlying ON prices_future_continuous(underlying, date DESC);
CREATE INDEX idx_prices_fut_cont_date ON prices_future_continuous(date);

-- 指数价格表
CREATE TABLE IF NOT EXISTS prices_index (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,                  -- 指数代码，如 "000300.SH"
    date DATE NOT NULL,                           -- 交易日期
    open DECIMAL(12, 4),                          -- 开盘价
    high DECIMAL(12, 4),                          -- 最高价
    low DECIMAL(12, 4),                           -- 最低价
    close DECIMAL(12, 4),                         -- 收盘价
    volume BIGINT,                                -- 成交量
    amount DECIMAL(20, 4),                        -- 成交金额
    pe_ttm DECIMAL(10, 4),                        -- 市盈率TTM
    pb_lf DECIMAL(10, 4),                         -- 市净率LF
    dividend_yield DECIMAL(8, 4),                 -- 股息率
    UNIQUE(symbol, date),
    FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_prices_index_symbol_date ON prices_index(symbol, date DESC);

-- 为已存在的表添加 update_time 字段（如果尚不存在）
ALTER TABLE prices_index ADD COLUMN IF NOT EXISTS update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 综合价格视图（统一查询接口）
CREATE OR REPLACE VIEW prices_unified AS
SELECT
    symbol, date, open, high, low, close, volume, amount,
    'stock' as asset_class
FROM prices_stock
UNION ALL
SELECT
    underlying as symbol, date,
    NULL as open, NULL as high, NULL as low,
    continuous_price as close, volume, NULL as amount,
    'future_continuous' as asset_class
FROM prices_future_continuous
UNION ALL
SELECT
    symbol, date, open, high, low, close, volume, amount,
    'index' as asset_class
FROM prices_index;

-- --------------------------------------------------------
-- 3. 因子数据表
-- --------------------------------------------------------

-- 大类资产因子表
CREATE TABLE IF NOT EXISTS factors_asset (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,                  -- 标的代码
    date DATE NOT NULL,                           -- 日期
    factor_name VARCHAR(50) NOT NULL,             -- 因子名称
    factor_value DECIMAL(20, 8),                  -- 因子值
    factor_group VARCHAR(20),                     -- 因子分组：value/growth/momentum/volatility/quality
    calculation_window INTEGER,                   -- 计算窗口（如20日、60日）
    UNIQUE(symbol, date, factor_name, calculation_window)
);

CREATE INDEX idx_factors_asset_symbol_date ON factors_asset(symbol, date DESC);
CREATE INDEX idx_factors_asset_name ON factors_asset(factor_name, date);

-- 商品期货因子表（展期、基差等专用）
CREATE TABLE IF NOT EXISTS factors_commodity (
    id BIGSERIAL PRIMARY KEY,
    underlying VARCHAR(10) NOT NULL,              -- 品种代码
    date DATE NOT NULL,                           -- 日期
    factor_name VARCHAR(50) NOT NULL,             -- 因子名称
    factor_value DECIMAL(20, 8),                  -- 因子值
    contract_1 VARCHAR(20),                       -- 近月合约
    contract_2 VARCHAR(20),                       -- 远月合约
    UNIQUE(underlying, date, factor_name)
);

CREATE INDEX idx_factors_comm_underlying ON factors_commodity(underlying, date DESC);

-- --------------------------------------------------------
-- 4. 汇率表
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fx_rates (
    id BIGSERIAL PRIMARY KEY,
    from_currency VARCHAR(3) NOT NULL,            -- 原币种
    to_currency VARCHAR(3) NOT NULL,              -- 目标币种
    date DATE NOT NULL,                           -- 日期
    spot_rate DECIMAL(12, 6),                     -- 即期汇率
    forward_1m DECIMAL(12, 6),                    -- 1月远期
    forward_3m DECIMAL(12, 6),                    -- 3月远期
    UNIQUE(from_currency, to_currency, date)
);

CREATE INDEX idx_fx_rates_pair ON fx_rates(from_currency, to_currency, date DESC);

-- 为已存在的表添加 update_time 字段（如果尚不存在）
ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- --------------------------------------------------------
-- 5. 宏观经济与市场指标表（用于择时、止损）
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS macro_indicators (
    id BIGSERIAL PRIMARY KEY,
    indicator_code VARCHAR(30) NOT NULL,          -- 指标代码
    indicator_name VARCHAR(100),                  -- 指标名称
    date DATE NOT NULL,                           -- 发布日期
    period_type VARCHAR(10),                      -- 周期：daily/weekly/monthly/quarterly/yearly
    value DECIMAL(20, 6),                         -- 指标值
    value_yoy DECIMAL(10, 4),                     -- 同比
    value_mom DECIMAL(10, 4),                     -- 环比
    unit VARCHAR(20),                             -- 单位
    UNIQUE(indicator_code, date)
);

CREATE INDEX idx_macro_ind_code ON macro_indicators(indicator_code, date DESC);

-- 为已存在的表添加 update_time 字段（如果尚不存在）
ALTER TABLE macro_indicators ADD COLUMN IF NOT EXISTS update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 市场状态表（综合择时指标）
CREATE TABLE IF NOT EXISTS market_regime (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,                           -- 日期
    market VARCHAR(20) NOT NULL,                  -- 市场：A股/美股/商品等
    regime VARCHAR(20),                           -- 市场状态：bull/bear/sideways/high_vol
    risk_score DECIMAL(5, 2),                     -- 风险评分 0-100
    sentiment_score DECIMAL(5, 2),                -- 情绪评分 -100到100
    liquidity_score DECIMAL(5, 2),                -- 流动性评分 0-100
    stop_loss_signal BOOLEAN DEFAULT FALSE,       -- 止损信号
    rebalance_signal BOOLEAN DEFAULT FALSE,       -- 再平衡信号
    UNIQUE(date, market)
);

CREATE INDEX idx_market_regime_date ON market_regime(date DESC);
CREATE INDEX idx_market_regime_market ON market_regime(market, date DESC);

-- --------------------------------------------------------
-- 6. 策略管理表
-- --------------------------------------------------------

-- 策略主表
CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL UNIQUE,    -- 策略代码
    strategy_name VARCHAR(100),                   -- 策略名称
    strategy_type VARCHAR(20),                    -- 策略类型：cta/equity/arbitrage/multi_asset
    asset_classes VARCHAR(50)[],                  -- 涉及资产类别
    benchmark VARCHAR(20),                        -- 业绩基准，如 "000300.SH"
    inception_date DATE,                          -- 成立日期
    status VARCHAR(10) DEFAULT 'active',          -- 状态：active/paused/stopped
    description TEXT,                             -- 策略描述
    parameters JSONB,                             -- 策略参数（JSON格式）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 策略净值表
CREATE TABLE IF NOT EXISTS strategy_nav (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    date DATE NOT NULL,                           -- 日期
    nav DECIMAL(12, 6) NOT NULL,                  -- 单位净值
    cumulative_nav DECIMAL(12, 6),                -- 累计净值
    daily_return DECIMAL(10, 6),                  -- 日收益率
    log_return DECIMAL(10, 6),                    -- 对数收益率
    aum DECIMAL(20, 4),                           -- 管理规模
    shares_outstanding BIGINT,                    -- 份额
    benchmark_nav DECIMAL(12, 6),                 -- 基准净值
    excess_return DECIMAL(10, 6),                 -- 超额收益
    drawdown DECIMAL(10, 6),                      -- 回撤
    is_backtest BOOLEAN DEFAULT FALSE,            -- 是否回测数据
    UNIQUE(strategy_code, date),
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

CREATE INDEX idx_strategy_nav_code_date ON strategy_nav(strategy_code, date DESC);
CREATE INDEX idx_strategy_nav_date ON strategy_nav(date);

-- --------------------------------------------------------
-- 7. 交易与持仓表
-- --------------------------------------------------------

-- 目标持仓表（策略信号生成的目标持仓）
CREATE TABLE IF NOT EXISTS target_positions (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    symbol VARCHAR(20) NOT NULL,                  -- 标的代码
    date DATE NOT NULL,                           -- 日期
    target_weight DECIMAL(8, 4),                  -- 目标权重 0-1
    target_shares BIGINT,                         -- 目标股数
    signal_direction INTEGER,                     -- 信号方向：1多头/-1空头/0平仓
    signal_strength DECIMAL(5, 2),                -- 信号强度 0-1
    reason VARCHAR(200),                          -- 信号原因
    UNIQUE(strategy_code, symbol, date),
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

CREATE INDEX idx_target_pos_code_date ON target_positions(strategy_code, date DESC);
CREATE INDEX idx_target_pos_symbol ON target_positions(symbol, date DESC);

-- 实际持仓表（执行后的实际持仓）
CREATE TABLE IF NOT EXISTS actual_positions (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    symbol VARCHAR(20) NOT NULL,                  -- 标的代码
    date DATE NOT NULL,                           -- 日期
    shares BIGINT NOT NULL,                       -- 持仓数量
    market_value DECIMAL(20, 4),                  -- 市值
    weight DECIMAL(8, 4),                         -- 权重
    avg_cost DECIMAL(12, 4),                      -- 平均成本
    unrealized_pnl DECIMAL(20, 4),                -- 浮动盈亏
    realized_pnl_ytd DECIMAL(20, 4),              -- 本年已实现盈亏
    days_held INTEGER,                            -- 持仓天数
    UNIQUE(strategy_code, symbol, date),
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

CREATE INDEX idx_actual_pos_code_date ON actual_positions(strategy_code, date DESC);
CREATE INDEX idx_actual_pos_symbol ON actual_positions(symbol, date DESC);

-- 交易记录表
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    symbol VARCHAR(20) NOT NULL,                  -- 标的代码
    trade_date DATE NOT NULL,                     -- 交易日期
    trade_time TIME,                              -- 交易时间
    direction VARCHAR(10) NOT NULL,               -- 方向：BUY/SELL
    quantity BIGINT NOT NULL,                     -- 成交数量
    price DECIMAL(12, 4) NOT NULL,                -- 成交价格
    amount DECIMAL(20, 4),                        -- 成交金额
    commission DECIMAL(12, 4),                    -- 手续费
    slippage DECIMAL(12, 4),                      -- 滑点成本
    trade_type VARCHAR(20),                       -- 交易类型：OPEN/CLOSE/ROLLOVER/REBALANCE
    related_signal_id BIGINT,                     -- 关联信号ID
    execution_venue VARCHAR(20),                  -- 执行场所
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

CREATE INDEX idx_trades_code_date ON trades(strategy_code, trade_date DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol, trade_date DESC);

-- --------------------------------------------------------
-- 8. 展期专用表（期货策略）
-- --------------------------------------------------------

-- 展期执行记录表
CREATE TABLE IF NOT EXISTS roll_executions (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    underlying VARCHAR(10) NOT NULL,              -- 品种代码
    roll_date DATE NOT NULL,                      -- 展期日期
    from_contract VARCHAR(20) NOT NULL,           -- 原合约
    to_contract VARCHAR(20) NOT NULL,             -- 目标合约
    roll_quantity BIGINT,                         -- 展期数量
    close_price DECIMAL(12, 4),                   -- 平仓价格
    open_price DECIMAL(12, 4),                    -- 开仓价格
    roll_cost DECIMAL(12, 4),                     -- 展期成本
    roll_type VARCHAR(20),                        -- 展期类型：scheduled/forced/early
    pnl_impact DECIMAL(12, 4),                    -- 对净值影响
    UNIQUE(strategy_code, underlying, roll_date),
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

-- --------------------------------------------------------
-- 9. 辅助表
-- --------------------------------------------------------

-- 指数成分股表
CREATE TABLE IF NOT EXISTS index_components (
    id BIGSERIAL PRIMARY KEY,
    index_symbol VARCHAR(20) NOT NULL,            -- 指数代码
    component_symbol VARCHAR(20) NOT NULL,        -- 成分股代码
    date DATE NOT NULL,                           -- 日期
    weight DECIMAL(8, 4),                         -- 权重
    is_active BOOLEAN DEFAULT TRUE,               -- 是否在当前成分中
    UNIQUE(index_symbol, component_symbol, date),
    FOREIGN KEY (index_symbol) REFERENCES assets(symbol) ON DELETE CASCADE,
    FOREIGN KEY (component_symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_index_comp_index ON index_components(index_symbol, date DESC);

-- 行业分类表
CREATE TABLE IF NOT EXISTS industry_classification (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,           -- 标的代码
    level_1_code VARCHAR(10),                     -- 一级行业代码
    level_1_name VARCHAR(50),                     -- 一级行业名称
    level_2_code VARCHAR(10),                     -- 二级行业代码
    level_2_name VARCHAR(50),                     -- 二级行业名称
    level_3_code VARCHAR(10),                     -- 三级行业代码
    level_3_name VARCHAR(50),                     -- 三级行业名称
    effective_date DATE,                          -- 生效日期
    FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

-- --------------------------------------------------------
-- 10. 更新触发器
-- --------------------------------------------------------

-- 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- --------------------------------------------------------
-- 11. 对冲策略专用表
-- --------------------------------------------------------

-- 对冲工具映射表（同一标的的多对冲工具选择）
CREATE TABLE IF NOT EXISTS hedge_instrument_mapping (
    id SERIAL PRIMARY KEY,
    underlying_index VARCHAR(20) NOT NULL,        -- 标的指数，如 "000300.SH" (沪深300)
    hedge_symbol VARCHAR(20) NOT NULL,            -- 对冲工具代码
    hedge_type VARCHAR(20) NOT NULL,              -- 对冲类型：index_future/etf/index_enhanced/synthetic
    hedge_name VARCHAR(100),                      -- 对冲工具名称
    tracking_index VARCHAR(20),                   -- 跟踪的指数（ETF/指增可能跟踪不同指数）
    expense_ratio DECIMAL(6, 4),                  -- 费率（ETF/指增的管理费）
    tracking_error DECIMAL(8, 4),                 -- 跟踪误差
    is_active BOOLEAN DEFAULT TRUE,               -- 是否可用
    start_date DATE,                              -- 上市/可用日期
    end_date DATE,                                -- 退市/停止日期
    priority INTEGER DEFAULT 1,                   -- 优先级（用于默认选择）
    description TEXT,                             -- 说明
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(underlying_index, hedge_symbol),
    FOREIGN KEY (underlying_index) REFERENCES assets(symbol) ON DELETE CASCADE,
    FOREIGN KEY (hedge_symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_hedge_map_underlying ON hedge_instrument_mapping(underlying_index);
CREATE INDEX idx_hedge_map_symbol ON hedge_instrument_mapping(hedge_symbol);
CREATE INDEX idx_hedge_map_type ON hedge_instrument_mapping(hedge_type);

-- 合成指数序列表（用于期货未上市时的指数拼接）
CREATE TABLE IF NOT EXISTS synthetic_index_series (
    id BIGSERIAL PRIMARY KEY,
    underlying_index VARCHAR(20) NOT NULL,        -- 标的指数
    date DATE NOT NULL,                           -- 日期
    close DECIMAL(12, 4),                         -- 收盘价
    source_type VARCHAR(20),                      -- 来源：index/future/etf/composite
    source_symbol VARCHAR(20),                    -- 来源代码
    is_interpolated BOOLEAN DEFAULT FALSE,        -- 是否插值（用于非交易日）
    interpolation_method VARCHAR(20),             -- 插值方法
    data_quality_score DECIMAL(3, 2),             -- 数据质量评分 0-1
    UNIQUE(underlying_index, date),
    FOREIGN KEY (underlying_index) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_synthetic_idx_underlying ON synthetic_index_series(underlying_index, date DESC);

-- 策略指数计算表（同一策略使用不同对冲工具计算的指数点位）
CREATE TABLE IF NOT EXISTS strategy_index_series (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    underlying_index VARCHAR(20) NOT NULL,        -- 标的指数
    hedge_symbol VARCHAR(20) NOT NULL,            -- 使用的对冲工具
    hedge_type VARCHAR(20) NOT NULL,              -- 对冲类型
    date DATE NOT NULL,                           -- 日期
    index_value DECIMAL(12, 4) NOT NULL,          -- 策略指数点位
    daily_return DECIMAL(10, 6),                  -- 日收益率
    cumulative_return DECIMAL(12, 6),             -- 累计收益率
    alpha DECIMAL(10, 6),                         -- 超额收益
    beta DECIMAL(8, 4),                           -- Beta
    tracking_error DECIMAL(10, 6),                -- 跟踪误差
    information_ratio DECIMAL(8, 4),              -- 信息比率
    hedge_cost DECIMAL(10, 6),                    -- 对冲成本
    roll_cost DECIMAL(10, 6),                     -- 展期成本（期货用）
    financing_cost DECIMAL(10, 6),                -- 资金成本
    is_backtest BOOLEAN DEFAULT FALSE,            -- 是否回测数据
    UNIQUE(strategy_code, underlying_index, hedge_symbol, date),
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE,
    FOREIGN KEY (hedge_symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_strat_idx_series ON strategy_index_series(strategy_code, date DESC);
CREATE INDEX idx_strat_idx_hedge ON strategy_index_series(strategy_code, hedge_symbol, date DESC);

-- 对冲工具比较表（同一策略不同对冲工具的表现对比）
CREATE TABLE IF NOT EXISTS hedge_comparison (
    id BIGSERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    underlying_index VARCHAR(20) NOT NULL,        -- 标的指数
    date DATE NOT NULL,                           -- 日期
    hedge_symbol_1 VARCHAR(20) NOT NULL,          -- 对冲工具1
    hedge_symbol_2 VARCHAR(20) NOT NULL,          -- 对冲工具2
    return_diff DECIMAL(10, 6),                   -- 收益差异
    cost_diff DECIMAL(10, 6),                     -- 成本差异
    tracking_diff DECIMAL(10, 6),                 -- 跟踪差异
    recommendation VARCHAR(20),                   -- 推荐：hedge_1/hedge_2/neutral
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE
);

CREATE INDEX idx_hedge_comp ON hedge_comparison(strategy_code, date DESC);

-- 策略对冲配置表（记录策略当前使用的对冲工具配置）
CREATE TABLE IF NOT EXISTS strategy_hedge_config (
    id SERIAL PRIMARY KEY,
    strategy_code VARCHAR(30) NOT NULL,           -- 策略代码
    underlying_index VARCHAR(20) NOT NULL,        -- 标的指数
    primary_hedge VARCHAR(20) NOT NULL,           -- 主对冲工具
    secondary_hedge VARCHAR(20),                  -- 备用对冲工具
    hedge_ratio DECIMAL(5, 4) DEFAULT 1.0,        -- 对冲比例
    roll_start_days INTEGER DEFAULT 10,           -- 展期观察窗口p
    roll_end_days INTEGER DEFAULT 3,              -- 展期强制窗口q
    use_synthetic BOOLEAN DEFAULT FALSE,          -- 是否使用合成指数
    switch_threshold DECIMAL(5, 4),               -- 切换阈值（成本差异超过此值切换）
    auto_switch BOOLEAN DEFAULT FALSE,            -- 是否自动切换
    effective_date DATE NOT NULL,                 -- 生效日期
    expiry_date DATE,                             -- 失效日期
    is_active BOOLEAN DEFAULT TRUE,               -- 是否生效
    FOREIGN KEY (strategy_code) REFERENCES strategies(strategy_code) ON DELETE CASCADE,
    FOREIGN KEY (primary_hedge) REFERENCES assets(symbol) ON DELETE CASCADE,
    FOREIGN KEY (secondary_hedge) REFERENCES assets(symbol) ON DELETE CASCADE
);

CREATE INDEX idx_strat_hedge_config ON strategy_hedge_config(strategy_code, effective_date DESC);

-- --------------------------------------------------------
-- 表注释（中文描述）
-- --------------------------------------------------------

COMMENT ON TABLE assets IS '资产主表：统一管理所有可交易标的（股票、期货、ETF、指数等）';
COMMENT ON TABLE trade_calendar IS '交易日历：记录各交易所的交易日、假日信息';

COMMENT ON TABLE prices_stock IS '股票价格表：股票和ETF的前复权日频行情数据';
COMMENT ON TABLE prices_future IS '期货价格表：期货原始合约的日频行情数据（含结算价、持仓量）';
COMMENT ON TABLE prices_future_continuous IS '期货连续合约表：展期处理后的连续价格序列（支持双窗口p/q参数）';
COMMENT ON TABLE prices_index IS '指数价格表：指数日频行情及估值指标（PE/PB/股息率）';

COMMENT ON TABLE factors_asset IS '资产因子表：通用因子数据（价值、动量、波动率、质量等）';
COMMENT ON TABLE factors_commodity IS '商品因子表：商品期货专用因子（展期收益、基差等）';

COMMENT ON TABLE fx_rates IS '汇率表：外汇即期和远期汇率数据';
COMMENT ON TABLE macro_indicators IS '宏观经济指标表：GDP、CPI、PMI等宏观数据';
COMMENT ON TABLE market_regime IS '市场状态表：市场状态分类（牛/熊/震荡/高波动）及择时信号';

COMMENT ON TABLE strategies IS '策略主表：策略基本信息、参数配置';
COMMENT ON TABLE strategy_nav IS '策略净值表：策略每日净值、收益率、回撤等业绩指标';
COMMENT ON TABLE target_positions IS '目标持仓表：策略生成的目标权重和交易信号';
COMMENT ON TABLE actual_positions IS '实际持仓表：实际执行的持仓和盈亏情况';
COMMENT ON TABLE trades IS '交易记录表：成交明细（价格、数量、成本、滑点）';
COMMENT ON TABLE roll_executions IS '展期执行记录表：期货合约换月执行记录及成本';

COMMENT ON TABLE index_components IS '指数成分股表：指数成分及其权重变化';
COMMENT ON TABLE industry_classification IS '行业分类表：股票的行业分类（一级/二级/三级）';

COMMENT ON TABLE hedge_instrument_mapping IS '对冲工具映射表：同一标的指数的多对冲工具配置（期货/ETF/指增）';
COMMENT ON TABLE synthetic_index_series IS '合成指数序列表：期货未上市时期的指数拼接数据';
COMMENT ON TABLE strategy_index_series IS '策略指数序列表：同一策略使用不同对冲工具计算的指数点位';
COMMENT ON TABLE hedge_comparison IS '对冲工具比较表：不同对冲工具的收益/成本对比';
COMMENT ON TABLE strategy_hedge_config IS '策略对冲配置表：策略当前使用的对冲工具及切换规则';

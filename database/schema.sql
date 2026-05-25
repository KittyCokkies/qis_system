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
    symbol VARCHAR(20) NOT NULL UNIQUE,           -- 标的代码，如 "IF2401"、"000001.SZ"
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

    CONSTRAINT chk_asset_class CHECK (asset_class IN ('stock', 'future', 'index', 'etf', 'bond', 'option', 'commodity'))
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

-- 期货价格表（原始合约数据）
CREATE TABLE IF NOT EXISTS prices_future (
    id BIGSERIAL PRIMARY KEY,
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
    UNIQUE(symbol, date),
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
    rollover_return DECIMAL(10, 6),               -- 展期收益
    days_to_expiry INTEGER,                       -- 距离到期天数
    is_rollover_day BOOLEAN DEFAULT FALSE,        -- 是否换仓日
    rollover_type VARCHAR(20),                    -- 换仓类型：hold/observation_roll/forced_roll
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
CREATE TABLE IF NOT EXISTS rollover_executions (
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

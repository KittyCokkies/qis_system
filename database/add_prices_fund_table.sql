-- ========================================================-- 添加场外基金净值表 (prices_fund)-- ========================================================

-- 创建场外基金净值表
CREATE TABLE IF NOT EXISTS prices_fund (
    symbol VARCHAR(20) NOT NULL,                  -- 基金代码，如 "007994.OF"
    date DATE NOT NULL,                           -- 日期
    nav DECIMAL(10, 4),                           -- 单位净值
    nav_adj DECIMAL(10, 4),                       -- 复权净值（用于计算收益）
    acc_nav DECIMAL(10, 4),                       -- 累计净值
    purchase_status VARCHAR(10),                  -- 申购状态：开放/关闭
    redeem_status VARCHAR(10),                    -- 赎回状态：开放/关闭
    dividend DECIMAL(10, 4),                      -- 分红金额
    split_ratio DECIMAL(10, 4),                   -- 拆分比例
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES assets(symbol) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX idx_prices_fund_symbol_date ON prices_fund(symbol, date DESC);
CREATE INDEX idx_prices_fund_date ON prices_fund(date);

-- 添加表注释
COMMENT ON TABLE prices_fund IS '场外基金净值表：存储开放式基金的每日净值数据（.OF后缀基金）';
COMMENT ON COLUMN prices_fund.symbol IS '基金代码，如 007994.OF';
COMMENT ON COLUMN prices_fund.nav IS '单位净值';
COMMENT ON COLUMN prices_fund.nav_adj IS '复权净值（考虑分红拆分后的连续价格）';
COMMENT ON COLUMN prices_fund.acc_nav IS '累计净值';
COMMENT ON COLUMN prices_fund.purchase_status IS '申购状态';
COMMENT ON COLUMN prices_fund.redeem_status IS '赎回状态';

-- 验证表创建成功
SELECT
    'prices_fund' as table_name,
    COUNT(*) as column_count
FROM information_schema.columns
WHERE table_name = 'prices_fund';

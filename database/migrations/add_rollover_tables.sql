-- ========================================================-- QIS System - Database Migration: Add Roll Configuration Tables-- Version: 1.0-- =========================================================

-- ---------------------------------------------------------- 1. Roll Configuration Table-- Stores all roll configurations from config/assets.yaml-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS roll_configs (
    config_id VARCHAR(30) PRIMARY KEY,
    -- 如: IF_S7q4_settle, RB_D72q34_close
    underlying VARCHAR(10) NOT NULL,
    -- 品种代码,如 IF, RB
    config_name VARCHAR(100),
    -- 配置中文名称
    roll_type VARCHAR(20) NOT NULL,
    -- static / dynamic
    price_type VARCHAR(20) NOT NULL,
    -- settle / close
    roll_start_days INTEGER NOT NULL,
    -- p: 到期前p天开始观察
    roll_end_days INTEGER NOT NULL,
    -- q: 到期前q天强制展期
    roll_window INTEGER DEFAULT 3,
    -- 展期窗口天数
    threshold DECIMAL(5, 4),
    -- 切换阈值th
    condition_type VARCHAR(20),
    -- open_interest / volume / null
    transaction_cost DECIMAL(10, 6) DEFAULT 0,
    -- 交易成本
    lead_months VARCHAR(50),
    -- 合约月份序列,如"1,5,9"
    start_date DATE,
    -- 数据开始日期
    data_source VARCHAR(20) NOT NULL DEFAULT 'tonglian',
    -- 数据源
    is_active BOOLEAN DEFAULT TRUE,
    -- 是否启用
    update_flag INTEGER DEFAULT 1,
    -- 是否更新(对应config中的update)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 约束
    CONSTRAINT chk_roll_type CHECK (roll_type IN ('static', 'dynamic')),
    CONSTRAINT chk_price_type CHECK (price_type IN ('settle', 'close')),
    CONSTRAINT chk_condition_type CHECK (condition_type IS NULL OR condition_type IN ('open_interest', 'volume'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_roll_underlying ON roll_configs(underlying);
CREATE INDEX IF NOT EXISTS idx_roll_active ON roll_configs(is_active);
CREATE INDEX IF NOT EXISTS idx_roll_update ON roll_configs(update_flag);
CREATE INDEX IF NOT EXISTS idx_roll_source ON roll_configs(data_source);

-- 注释
COMMENT ON TABLE roll_configs IS '期货展期配置表';
COMMENT ON COLUMN roll_configs.config_id IS '配置唯一ID,如IF_S7q4_settle';
COMMENT ON COLUMN roll_configs.underlying IS '品种代码';
COMMENT ON COLUMN roll_configs.roll_type IS '展期类型:static/dynamic';
COMMENT ON COLUMN roll_configs.price_type IS '价格类型:settle/close';
COMMENT ON COLUMN roll_configs.roll_start_days IS 'p:到期前p天开始观察';
COMMENT ON COLUMN roll_configs.roll_end_days IS 'q:到期前q天强制展期';
COMMENT ON COLUMN roll_configs.condition_type IS '动态展期条件:open_interest/volume';

-- --------------------------------------------------------
-- 2. Sync Logs Table
-- Tracks all data synchronization operations
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    sync_date DATE NOT NULL,
    -- 同步日期
    data_source VARCHAR(20) NOT NULL,
    -- tonglian / wind / bbg_excel
    asset_type VARCHAR(20),
    -- future / index / etf / concat
    asset_symbol VARCHAR(30),
    -- 具体资产代码(可选)
    status VARCHAR(20) NOT NULL,
    -- success / failed / partial / running
    records_count INTEGER,
    -- 同步记录数
    error_message TEXT,
    -- 错误信息
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 开始时间
    completed_at TIMESTAMP,
    -- 完成时间
    duration_seconds INTEGER,
    -- 耗时(秒)
    triggered_by VARCHAR(50)
    -- 触发者:manual/script/user
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_sync_logs_date ON sync_logs(sync_date DESC);
CREATE INDEX IF NOT EXISTS idx_sync_logs_source ON sync_logs(data_source);
CREATE INDEX IF NOT EXISTS idx_sync_logs_status ON sync_logs(status);
CREATE INDEX IF NOT EXISTS idx_sync_logs_date_source ON sync_logs(sync_date, data_source);

-- 注释
COMMENT ON TABLE sync_logs IS '数据同步日志表';
COMMENT ON COLUMN sync_logs.sync_date IS '同步日期';
COMMENT ON COLUMN sync_logs.data_source IS '数据源:tonglian/wind/bbg_excel';
COMMENT ON COLUMN sync_logs.status IS '同步状态:success/failed/partial/running';

-- --------------------------------------------------------
-- 3. Update prices_future_continuous table-- Add config_id column to link with roll_configs-- --------------------------------------------------------

-- 检查是否已存在config_id列
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'prices_future_continuous'
        AND column_name = 'config_id'
    ) THEN
        ALTER TABLE prices_future_continuous
        ADD COLUMN config_id VARCHAR(30);
    END IF;
END $$;

-- 添加外键约束(如果config_id列存在)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'prices_future_continuous'
        AND column_name = 'config_id'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_prices_fut_cont_config'
    ) THEN
        ALTER TABLE prices_future_continuous
        ADD CONSTRAINT fk_prices_fut_cont_config
        FOREIGN KEY (config_id) REFERENCES roll_configs(config_id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- 更新prices_future_continuous的索引
DROP INDEX IF EXISTS idx_prices_fut_cont_underlying;
CREATE INDEX IF NOT EXISTS idx_prices_fut_cont_config_date
ON prices_future_continuous(config_id, date DESC);

-- --------------------------------------------------------
-- 4. Concat Asset Configuration Table-- Stores concat asset definitions-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS concat_asset_configs (
    symbol VARCHAR(30) PRIMARY KEY,
    -- 合成资产代码,如CYB_CONCAT
    name VARCHAR(100) NOT NULL,
    -- 合成资产名称
    description TEXT,
    -- 描述
    asset_type VARCHAR(20) DEFAULT 'concat',
    -- concat / merged
    components JSONB NOT NULL,
    -- 组件列表(JSON格式)
    update_flag INTEGER DEFAULT 1,
    -- 是否更新
    is_active BOOLEAN DEFAULT TRUE,
    -- 是否启用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_concat_active ON concat_asset_configs(is_active);

-- 注释
COMMENT ON TABLE concat_asset_configs IS '合成资产配置表';
COMMENT ON COLUMN concat_asset_configs.symbol IS '合成资产代码';
COMMENT ON COLUMN concat_asset_configs.components IS '组件列表,JSON格式:[{"symbol":"XXX","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}]';

-- --------------------------------------------------------
-- 5. Data Source Configuration Table-- Stores data source connection info-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_source_configs (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(20) NOT NULL UNIQUE,
    -- tonglian / wind / bbg_excel
    source_type VARCHAR(20) NOT NULL,
    -- database / api / file / excel
    connection_info JSONB,
    -- 连接信息(JSON格式)
    priority INTEGER DEFAULT 1,
    -- 优先级
    is_active BOOLEAN DEFAULT TRUE,
    -- 是否启用
    last_sync_at TIMESTAMP,
    -- 最后同步时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入默认数据源配置
INSERT INTO data_source_configs (source_name, source_type, connection_info, priority, is_active)
VALUES
    ('tonglian', 'database', '{"host":"localhost","port":3306,"database":"tonglian"}', 1, TRUE)
ON CONFLICT (source_name) DO NOTHING;

INSERT INTO data_source_configs (source_name, source_type, connection_info, priority, is_active)
VALUES
    ('wind', 'api', '{"api_type":"windpy"}', 1, TRUE)
ON CONFLICT (source_name) DO NOTHING;

INSERT INTO data_source_configs (source_name, source_type, connection_info, priority, is_active)
VALUES
    ('bbg_excel', 'file', '{"file_pattern":"bbg_data_YYYYMMDD.xlsx","directory":"data/bbg_input"}', 1, TRUE)
ON CONFLICT (source_name) DO NOTHING;

-- 注释
COMMENT ON TABLE data_source_configs IS '数据源配置表';
COMMENT ON COLUMN data_source_configs.source_name IS '数据源名称';
COMMENT ON COLUMN data_source_configs.connection_info IS '连接信息,JSON格式';

-- --------------------------------------------------------
-- 6. Helper Functions-- --------------------------------------------------------

-- 更新updated_at时间戳的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为roll_configs添加触发器
DROP TRIGGER IF EXISTS update_roll_configs_updated_at ON roll_configs;
CREATE TRIGGER update_roll_configs_updated_at
    BEFORE UPDATE ON roll_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 为concat_asset_configs添加触发器
DROP TRIGGER IF EXISTS update_concat_configs_updated_at ON concat_asset_configs;
CREATE TRIGGER update_concat_configs_updated_at
    BEFORE UPDATE ON concat_asset_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- --------------------------------------------------------
-- 7. Initial Data Verification-- --------------------------------------------------------

-- 验证表是否创建成功
SELECT 'roll_configs' as table_name, COUNT(*) as record_count
FROM roll_configs
UNION ALL
SELECT 'sync_logs', COUNT(*) FROM sync_logs
UNION ALL
SELECT 'concat_asset_configs', COUNT(*) FROM concat_asset_configs
UNION ALL
SELECT 'data_source_configs', COUNT(*) FROM data_source_configs;

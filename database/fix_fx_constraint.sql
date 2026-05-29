-- 修复 assets 表 chk_asset_class 约束，添加 fx 支持
-- 先完全删除旧约束（如果存在）
DO $$
BEGIN
    -- 检查约束是否存在
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_asset_class'
        AND conrelid = 'assets'::regclass
    ) THEN
        -- 删除旧约束
        EXECUTE 'ALTER TABLE assets DROP CONSTRAINT chk_asset_class';
        RAISE NOTICE '已删除旧约束 chk_asset_class';
    END IF;
END $$;

-- 添加新约束（包含 fx）
ALTER TABLE assets ADD CONSTRAINT chk_asset_class
    CHECK (asset_class IN ('stock', 'future', 'index', 'etf', 'bond', 'option', 'commodity', 'fund', 'fx', 'macro'));

-- 验证修复结果
SELECT
    conname as constraint_name,
    pg_get_constraintdef(oid) as constraint_definition
FROM pg_constraint
WHERE conrelid = 'assets'::regclass
AND contype = 'c'
AND conname = 'chk_asset_class';

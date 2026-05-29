-- ========================================================-- 清理Airflow和旧系统表-- ========================================================--
-- 说明：-- 此脚本用于删除Airflow相关的42个系统表和2个旧系统表-- 执行前请确保已备份重要数据（虽然这些表都是Airflow元数据）
-- ========================================================

-- 开始事务
BEGIN;

-- ========================================================-- 第一步：删除外键依赖（防止外键约束错误）-- ========================================================

-- 删除ab_permission_view_role的外键
ALTER TABLE IF EXISTS ab_permission_view_role DROP CONSTRAINT IF EXISTS ab_permission_view_role_permission_view_id_fkey;
ALTER TABLE IF EXISTS ab_permission_view_role DROP CONSTRAINT IF EXISTS ab_permission_view_role_role_id_fkey;

-- 删除ab_permission_view的外键
ALTER TABLE IF EXISTS ab_permission_view DROP CONSTRAINT IF EXISTS ab_permission_view_permission_id_fkey;

-- 删除ab_user_role的外键
ALTER TABLE IF EXISTS ab_user_role DROP CONSTRAINT IF EXISTS ab_user_role_user_id_fkey;
ALTER TABLE IF EXISTS ab_user_role DROP CONSTRAINT IF EXISTS ab_user_role_role_id_fkey;

-- ========================================================-- 第二步：删除Airflow系统表（按依赖顺序）-- ========================================================

-- 任务相关表
DROP TABLE IF EXISTS task_instance_note CASCADE;
DROP TABLE IF EXISTS task_outlet_dataset_reference CASCADE;
DROP TABLE IF EXISTS task_reschedule CASCADE;
DROP TABLE IF EXISTS rendered_task_instance_fields CASCADE;
DROP TABLE IF EXISTS task_map CASCADE;
DROP TABLE IF EXISTS task_fail CASCADE;
DROP TABLE IF EXISTS task_instance CASCADE;

-- DAG运行相关表
DROP TABLE IF EXISTS dag_run_note CASCADE;
DROP TABLE IF EXISTS dagrun_dataset_event CASCADE;
DROP TABLE IF EXISTS dag_run CASCADE;

-- DAG定义相关表
DROP TABLE IF EXISTS dag_schedule_dataset_reference CASCADE;
DROP TABLE IF EXISTS dag_owner_attributes CASCADE;
DROP TABLE IF EXISTS dag_tag CASCADE;
DROP TABLE IF EXISTS dag_warning CASCADE;
DROP TABLE IF EXISTS dag_pickle CASCADE;
DROP TABLE IF EXISTS serialized_dag CASCADE;
DROP TABLE IF EXISTS dag_code CASCADE;
DROP TABLE IF EXISTS dag CASCADE;

-- 数据集相关表
DROP TABLE IF EXISTS dataset_dag_run_queue CASCADE;
DROP TABLE IF EXISTS dataset_event CASCADE;
DROP TABLE IF EXISTS dataset CASCADE;

-- 权限相关表（Flask-AppBuilder）
DROP TABLE IF EXISTS ab_permission_view_role CASCADE;
DROP TABLE IF EXISTS ab_permission_view CASCADE;
DROP TABLE IF EXISTS ab_permission CASCADE;
DROP TABLE IF EXISTS ab_view_menu CASCADE;
DROP TABLE IF EXISTS ab_user_role CASCADE;
DROP TABLE IF EXISTS ab_register_user CASCADE;
DROP TABLE IF EXISTS ab_user CASCADE;
DROP TABLE IF EXISTS ab_role CASCADE;

-- Airflow其他表
DROP TABLE IF EXISTS callback_request CASCADE;
DROP TABLE IF EXISTS connection CASCADE;
DROP TABLE IF EXISTS import_error CASCADE;
DROP TABLE IF EXISTS job CASCADE;
DROP TABLE IF EXISTS log_template CASCADE;
DROP TABLE IF EXISTS log CASCADE;
DROP TABLE IF EXISTS session CASCADE;
DROP TABLE IF EXISTS sla_miss CASCADE;
DROP TABLE IF EXISTS slot_pool CASCADE;
DROP TABLE IF EXISTS trigger CASCADE;
DROP TABLE IF EXISTS variable CASCADE;
DROP TABLE IF EXISTS xcom CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;

-- ========================================================-- 第三步：删除旧系统表-- ========================================================

DROP TABLE IF EXISTS roll_configs CASCADE;
DROP TABLE IF EXISTS rollover_executions CASCADE;

-- ========================================================-- 第四步：删除相关的序列（如果有）-- ========================================================

-- 删除与Airflow表相关的序列
DROP SEQUENCE IF EXISTS ab_permission_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ab_permission_view_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ab_view_menu_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ab_role_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ab_user_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ab_register_user_id_seq CASCADE;
DROP SEQUENCE IF EXISTS connection_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dag_dag_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dag_pickle_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dag_run_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dag_run_note_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dataset_id_seq CASCADE;
DROP SEQUENCE IF EXISTS dataset_event_id_seq CASCADE;
DROP SEQUENCE IF EXISTS import_error_id_seq CASCADE;
DROP SEQUENCE IF EXISTS job_id_seq CASCADE;
DROP SEQUENCE IF EXISTS log_template_id_seq CASCADE;
DROP SEQUENCE IF EXISTS slot_pool_id_seq CASCADE;
DROP SEQUENCE IF EXISTS task_instance_id_seq CASCADE;
DROP SEQUENCE IF EXISTS task_instance_note_id_seq CASCADE;
DROP SEQUENCE IF EXISTS trigger_id_seq CASCADE;
DROP SEQUENCE IF EXISTS variable_id_seq CASCADE;

-- ========================================================-- 提交事务
-- ========================================================

COMMIT;

-- 验证删除结果
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

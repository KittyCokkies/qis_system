"""
通联期货数据每日同步 DAG

功能：
- 每日收盘后自动同步通联期货数据到本地 PostgreSQL
- 支持自动识别所有配置的品种
- 包含合约信息更新和价格数据同步
- 失败自动重试，支持手动触发指定日期

调度：工作日 17:30（期货收盘后）
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.exceptions import AirflowFailException
from airflow.utils.task_group import TaskGroup

# 添加项目路径
sys.path.insert(0, '/opt/qis_system')

# 导入项目模块
from loguru import logger
import pandas as pd

# 日志配置（Airflow环境下）
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# =============================================================================
# 默认参数
# =============================================================================

DEFAULT_ARGS = {
    'owner': 'qis',
    'depends_on_past': False,  # 不依赖前一日成功
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# 项目根目录
PROJECT_ROOT = Path('/opt/qis_system')


def get_tonglian_source():
    """获取通联数据源（延迟导入避免DAG解析时连接）"""
    from data.tonglian_source import TonglianSource
    return TonglianSource()


def get_database_manager():
    """获取数据库管理器"""
    from data.database import DatabaseManager
    return DatabaseManager()


def get_config_loader():
    """获取配置加载器"""
    from data.config.loader import AssetConfigLoader
    loader = AssetConfigLoader()
    loader.load()
    return loader


def get_active_futures() -> List[str]:
    """获取所有活跃的期货品种代码"""
    try:
        loader = get_config_loader()
        underlyings = list(loader.futures.keys())
        logger.info(f"从配置加载了 {len(underlyings)} 个期货品种")
        return underlyings
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        raise AirflowFailException(f"配置加载失败: {e}")


def import_contracts_for_underlying(underlying: str, **context) -> Dict[str, Any]:
    """
    导入指定品种的合约信息到 assets 表

    从通联 futu 表获取合约详情（乘数、tick_size、上市/退市日期等）
    """
    execution_date = context['execution_date']
    sync_date = execution_date.date()

    logger.info(f"[{underlying}] 开始导入合约信息，执行日期: {sync_date}")

    try:
        source = get_tonglian_source()
        db = get_database_manager()

        # 从 futu 表获取合约详情
        details = source.get_contract_details(underlying)

        if details.empty:
            logger.warning(f"[{underlying}] 在futu表未找到合约详情")
            return {'underlying': underlying, 'contracts': 0, 'status': 'no_data'}

        # 导入合约
        count = 0
        for _, row in details.iterrows():
            try:
                # 日期转换
                list_date = row.get('list_date')
                last_trade_date = row.get('last_trade_date')

                if pd.notna(list_date) and hasattr(list_date, 'date'):
                    list_date = list_date.date()
                if pd.notna(last_trade_date) and hasattr(last_trade_date, 'date'):
                    last_trade_date = last_trade_date.date()

                db.execute('''
                    INSERT INTO assets
                    (symbol, underlying, name, asset_class, exchange, is_active,
                     contract_month, list_date, delist_date, multiplier, tick_size)
                    VALUES (:symbol, :underlying, :name, :asset_class, :exchange, :is_active,
                            :contract_month, :list_date, :delist_date, :multiplier, :tick_size)
                    ON CONFLICT (symbol) DO UPDATE SET
                        contract_month = EXCLUDED.contract_month,
                        list_date = EXCLUDED.list_date,
                        delist_date = EXCLUDED.delist_date,
                        multiplier = EXCLUDED.multiplier,
                        tick_size = EXCLUDED.tick_size,
                        exchange = EXCLUDED.exchange,
                        updated_at = CURRENT_TIMESTAMP
                ''', {
                    'symbol': row['symbol'],
                    'underlying': underlying,
                    'name': row['symbol'],
                    'asset_class': 'future',
                    'exchange': row.get('exchange', 'CFFEX'),
                    'is_active': True,
                    'contract_month': row.get('contract_month'),
                    'list_date': list_date,
                    'delist_date': last_trade_date,
                    'multiplier': row.get('multiplier'),
                    'tick_size': row.get('tick_size')
                })
                count += 1
            except Exception as e:
                logger.warning(f"[{underlying}] 导入 {row.get('symbol')} 失败: {e}")

        logger.info(f"[{underlying}] 成功导入 {count} 个合约")
        return {
            'underlying': underlying,
            'contracts': count,
            'status': 'success'
        }

    except Exception as e:
        logger.error(f"[{underlying}] 合约导入失败: {e}")
        raise AirflowFailException(f"{underlying} 合约导入失败: {e}")


def sync_prices_for_underlying(underlying: str, **context) -> Dict[str, Any]:
    """
    同步指定品种在指定日期的价格数据
    """
    execution_date = context['execution_date']
    sync_date = execution_date.date()

    logger.info(f"[{underlying}] 开始同步价格数据，日期: {sync_date}")

    try:
        from data.sync.tonglian_sync import TonglianSync

        sync = TonglianSync()

        # 同步单日数据
        records = sync.sync_daily_data(underlying, sync_date, full_refresh=True)

        logger.info(f"[{underlying}] 同步完成: {records} 条记录")
        return {
            'underlying': underlying,
            'records': records,
            'date': str(sync_date),
            'status': 'success'
        }

    except Exception as e:
        logger.error(f"[{underlying}] 价格同步失败: {e}")
        raise AirflowFailException(f"{underlying} 价格同步失败: {e}")


def sync_single_underlying(underlying: str, **context) -> Dict[str, Any]:
    """
    同步单个品种（合约信息 + 价格数据）
    用于动态生成任务
    """
    execution_date = context['execution_date']
    sync_date = execution_date.date()

    logger.info(f"=" * 60)
    logger.info(f"开始同步品种: {underlying}, 日期: {sync_date}")
    logger.info(f"=" * 60)

    # 步骤1: 导入合约信息
    contract_result = import_contracts_for_underlying(underlying, **context)

    # 步骤2: 同步价格数据
    price_result = sync_prices_for_underlying(underlying, **context)

    return {
        'underlying': underlying,
        'date': str(sync_date),
        'contracts': contract_result['contracts'],
        'records': price_result['records']
    }


def summarize_results(**context) -> None:
    """
    汇总所有品种的同步结果
    """
    task_instances = context['ti']
    execution_date = context['execution_date']
    sync_date = execution_date.date()

    # 获取所有品种
    underlyings = get_active_futures()

    total_contracts = 0
    total_records = 0
    success_count = 0
    failed_count = 0

    logger.info("\n" + "=" * 80)
    logger.info("通联期货数据同步汇总")
    logger.info(f"同步日期: {sync_date}")
    logger.info("=" * 80)

    for underlying in underlyings:
        try:
            # 获取该品种的XCom结果
            result = task_instances.xcom_pull(
                task_ids=f'sync_underlyings.sync_{underlying}',
                key='return_value'
            )

            if result:
                total_contracts += result.get('contracts', 0)
                total_records += result.get('records', 0)
                success_count += 1
                logger.info(f"{underlying:6} | 合约: {result.get('contracts', 0):4} | 记录: {result.get('records', 0):6}")
            else:
                failed_count += 1
                logger.error(f"{underlying:6} | 无返回数据")

        except Exception as e:
            failed_count += 1
            logger.error(f"{underlying:6} | 获取结果失败: {e}")

    logger.info("-" * 80)
    logger.info(f"{'合计':6} | 成功: {success_count}/{len(underlyings)} | 合约: {total_contracts} | 记录: {total_records}")
    logger.info("=" * 80)

    # 如果有失败，抛出异常
    if failed_count > 0:
        raise AirflowFailException(f"{failed_count} 个品种同步失败")


# =============================================================================
# DAG 定义
# =============================================================================

with DAG(
    dag_id='sync_tonglian_futures_daily',
    default_args=DEFAULT_ARGS,
    description='每日同步通联期货数据到本地数据库',
    # 工作日 17:30 执行（期货收盘后）
    schedule='30 17 * * 1-5',
    start_date=datetime(2024, 1, 1),
    catchup=False,  # 不补跑历史
    max_active_runs=1,  # 同时只能运行一个实例
    tags=['futures', 'tonglian', 'daily-sync'],
    doc_md="""
    # 通联期货数据每日同步

    ## 功能
    - 自动同步所有配置品种（assets.yaml）的期货数据
    - 更新合约信息（乘数、tick_size、上市/退市日期）
    - 同步日频价格数据（开高低收、结算价、持仓量等）

    ## 调度
    - 时间：工作日 17:30（期货收盘后）
    - 重试：失败时重试3次，间隔5分钟

    ## 手动触发
    ```bash
    airflow dags trigger sync_tonglian_futures_daily --exec-date 2026-05-26
    ```

    ## 依赖
    - 通联数据库连接
    - 本地 PostgreSQL 数据库
    """,
) as dag:

    # 开始标记
    start = EmptyOperator(task_id='start')

    # 获取品种列表任务
    get_underlyings_task = PythonOperator(
        task_id='get_underlyings',
        python_callable=get_active_futures,
    )

    # 为每个品种创建同步任务组
    underlyings = get_active_futures()

    with TaskGroup(
        group_id='sync_underlyings',
        prefix_group_id=False,
    ) as sync_group:

        for underlying in underlyings:
            PythonOperator(
                task_id=f'sync_{underlying}',
                python_callable=sync_single_underlying,
                op_kwargs={'underlying': underlying},
            )

    # 汇总结果
    summarize = PythonOperator(
        task_id='summarize_results',
        python_callable=summarize_results,
        trigger_rule='all_done',  # 无论成功失败都执行汇总
    )

    # 结束标记
    end = EmptyOperator(task_id='end')

    # 任务流
    start >> get_underlyings_task >> sync_group >> summarize >> end

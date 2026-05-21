#!/usr/bin/env python3
"""
QIS System - 量化投资策略系统主入口

Usage:
    python main.py backtest --strategy allocation --config config/allocation.yaml
    python main.py data --command update --source akshare
    python main.py research --notebook examples/test_allocation
"""

import click
from loguru import logger

from config import get_settings
from utils import setup_logger


@click.group()
@click.option("--config", "-c", help="配置文件路径")
@click.option("--verbose", "-v", is_flag=True, help="详细日志输出")
def cli(config, verbose):
    """QIS System - 量化投资策略系统"""
    setup_logger(level="DEBUG" if verbose else "INFO")
    logger.info("QIS System started")


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称")
@click.option("--start-date", help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", help="结束日期 (YYYY-MM-DD)")
@click.option("--symbol", "-sym", multiple=True, help="标的代码")
def backtest(strategy, start_date, end_date, symbol):
    """运行回测"""
    logger.info(f"Running backtest: {strategy}")
    # TODO: 实现回测逻辑
    pass


@cli.command()
@click.option("--command", "-cmd", required=True,
              type=click.Choice(["update", "clean", "check"]))
@click.option("--source", help="数据源 (akshare/tushare)")
@click.option("--start-date", help="开始日期")
@click.option("--end-date", help="结束日期")
def data(command, source, start_date, end_date):
    """数据管理"""
    logger.info(f"Data command: {command}")
    # TODO: 实现数据管理逻辑
    pass


@cli.command()
@click.option("--script", help="运行研究脚本")
@click.option("--notebook", help="启动Jupyter notebook")
def research(script, notebook):
    """研究模式"""
    if script:
        logger.info(f"Running research script: {script}")
        exec(open(f"research/{script}.py").read())
    elif notebook:
        import subprocess
        subprocess.run(["jupyter", "notebook", f"research/{notebook}"])


@cli.command()
def version():
    """显示版本信息"""
    click.echo("QIS System v0.1.0")


if __name__ == "__main__":
    cli()

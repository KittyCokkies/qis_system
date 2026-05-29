#!/usr/bin/env python3
"""
同步脚本日志配置模块
统一所有数据同步脚本的日志格式
"""
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger


def setup_logger(script_name: str):
    """
    设置统一格式的日志记录器

    Args:
        script_name: 脚本名称，用于生成日志文件名

    Returns:
        logger 实例
    """
    # 移除默认处理器
    logger.remove()

    # 生成带日期的日志文件名
    log_date = datetime.now().strftime('%Y-%m-%d')
    log_file = f'logs/sync_{script_name}_{log_date}.log'

    # 定义格式化函数，确保对齐
    # 格式: TIME | LEVEL | SCRIPT | MESSAGE
    # 各列宽度: 19 | 8 | 15 | ...
    def format_record(record):
        script = record["extra"].get("script", "UNKNOWN")
        time_str = record["time"].strftime('%Y-%m-%d %H:%M:%S')
        level_str = f"{record['level'].name:<8}"
        script_str = f"{script:<15}"
        return f"{time_str} | {level_str} | {script_str} | {record['message']}\n"

    # 添加控制台输出
    logger.add(
        sys.stdout,
        level="INFO",
        format=format_record,
        colorize=True
    )

    # 添加文件输出
    logger.add(
        log_file,
        level="INFO",
        format=format_record,
        rotation="1 day",
        retention="7 days",
        encoding="utf-8"
    )

    # 绑定脚本名称
    return logger.bind(script=script_name.upper())

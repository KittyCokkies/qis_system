import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    log_file: str = "logs/qis_system.log",
    level: str = "INFO",
    rotation: str = "10 MB"
):
    """配置日志

    Args:
        log_file: 日志文件路径
        level: 日志级别
        rotation: 日志轮转大小
    """
    # 移除默认处理器
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>"
    )

    # 添加文件输出
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_file,
        level=level,
        rotation=rotation,
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
    )

    return logger
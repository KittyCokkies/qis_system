"""
数据源管理器示例

演示如何使用DataManager统一访问多个数据源
"""
from datetime import datetime, timedelta

from loguru import logger

from data import DataManager, WindSource, TonglianSource, FTPSource
from utils import setup_logger


def test_data_manager():
    """测试数据管理器"""
    logger.info("=" * 60)
    logger.info("测试 数据源管理器 (DataManager)")
    logger.info("=" * 60)

    # 创建管理器
    manager = DataManager(
        priority=["tonglian", "wind", "akshare"]  # 设置优先级
    )

    # 查看数据源可用性
    logger.info("\n数据源可用性:")
    availability = manager.get_data_availability()
    for name, available in availability.items():
        status = "✓" if available else "✗"
        logger.info(f"  {status} {name}")

    # 测试获取数据
    symbol = "000001.SZ"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    logger.info(f"\n获取 {symbol} 日频数据...")
    df = manager.get_daily_price(
        symbol,
        start_date=start_date,
        end_date=end_date,
        use_cache=True
    )

    if not df.empty:
        logger.info(f"获取成功: {len(df)} 条记录")
        logger.info(f"数据列: {list(df.columns)}")
        logger.info(f"\n最近5条数据:\n{df.tail()}")
    else:
        logger.warning("获取数据失败或数据为空")

    # 测试获取指数成分股
    logger.info("\n获取沪深300成分股...")
    components = manager.get_index_components("000300.SH")
    if components:
        logger.info(f"获取成功: {len(components)} 只股票")
        logger.info(f"前10只: {components[:10]}")

    # 测试获取交易日历
    logger.info("\n获取本月交易日历...")
    calendar = manager.get_trade_calendar(
        start_date=start_date,
        end_date=end_date,
        market="SSE"
    )
    if not calendar.empty:
        logger.info(f"交易日数量: {len(calendar)}")


def test_wind_source():
    """测试Wind数据源"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 Wind数据源")
    logger.info("=" * 60)

    wind = WindSource()

    if not wind.is_connected:
        logger.warning("Wind未连接（请确保已安装WindPy并启动Wind终端）")
        return

    logger.info("Wind已连接")

    # 获取数据示例
    symbol = "000001.SZ"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    logger.info(f"\n获取 {symbol} 数据...")
    df = wind.get_daily_price(symbol, start_date, end_date)

    if not df.empty:
        logger.info(f"获取成功: {len(df)} 条记录")
        logger.info(f"\n{df.head()}")


def test_tonglian_source():
    """测试通联数据源"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 通联数据源")
    logger.info("=" * 60)

    tonglian = TonglianSource()

    # 测试连接
    logger.info("\n测试数据库连接...")
    if tonglian.test_connection():
        logger.info("通联数据库连接成功")
    else:
        logger.error("通联数据库连接失败")
        return

    # 获取股票日行情
    symbol = "000001"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    logger.info(f"\n获取 {symbol} 日行情...")
    df = tonglian.get_daily_price(symbol, start_date, end_date)

    if not df.empty:
        logger.info(f"获取成功: {len(df)} 条记录")
        logger.info(f"数据列: {list(df.columns)}")
        logger.info(f"\n最近5条:\n{df.tail()}")

    # 获取财务数据
    logger.info(f"\n获取 {symbol} 财务数据...")
    fund = tonglian.get_fundamentals(symbol, date=end_date)

    if not fund.empty:
        logger.info(f"获取成功: {len(fund)} 条记录")
        logger.info(f"\n{fund.head()}")

    # 获取指数成分股
    logger.info("\n获取沪深300成分股...")
    components = tonglian.get_index_components("000300")
    if components:
        logger.info(f"成分股数量: {len(components)}")
        logger.info(f"前10只: {components[:10]}")


def test_ftp_source():
    """测试FTP数据源"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 FTP数据源")
    logger.info("=" * 60)

    # FTP需要配置后才能使用
    ftp = FTPSource()

    if not ftp.ensure_connected():
        logger.warning("FTP未连接（请先在配置中设置FTP参数）")
        return

    logger.info("FTP已连接")

    # 列出文件
    logger.info("\n列出远程文件...")
    files = ftp.list_files(pattern="*.csv")
    logger.info(f"找到 {len(files)} 个CSV文件")
    if files:
        logger.info(f"前5个: {files[:5]}")


def main():
    """主函数"""
    setup_logger()

    logger.info("\n" + "=" * 70)
    logger.info("QIS System 数据源管理器测试")
    logger.info("=" * 70)

    # 1. 测试数据管理器
    test_data_manager()

    # 2. 测试Wind
    test_wind_source()

    # 3. 测试通联
    test_tonglian_source()

    # 4. 测试FTP
    test_ftp_source()

    logger.info("\n" + "=" * 70)
    logger.info("数据源测试完成")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

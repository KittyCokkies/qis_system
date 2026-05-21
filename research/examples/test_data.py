"""
数据层使用示例

演示如何使用数据层获取和处理数据
"""

from datetime import datetime, timedelta

from loguru import logger

from data import AKShareSource, TushareSource, DatabaseManager
from utils import setup_logger


def test_akshare():
    """测试AKShare数据源"""
    logger.info("=" * 50)
    logger.info("测试AKShare数据源")
    logger.info("=" * 50)

    source = AKShareSource()

    # 获取单只股票数据
    symbol = "000001.SZ"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    logger.info(f"获取 {symbol} 数据...")
    df = source.get_daily_price(symbol, start_date, end_date)
    logger.info(f"获取到 {len(df)} 条记录")

    if not df.empty:
        logger.info(f"列名: {list(df.columns)}")
        logger.info(f"\n最近5条数据:\n{df.tail()}")

    # 获取指数成分股
    logger.info("\n获取沪深300成分股...")
    components = source.get_index_components("000300.SH")
    logger.info(f"成分股数量: {len(components)}")
    if components:
        logger.info(f"前10只: {components[:10]}")

    return df


def test_tushare():
    """测试Tushare数据源"""
    logger.info("\n" + "=" * 50)
    logger.info("测试Tushare数据源")
    logger.info("=" * 50)

    # 需要token
    source = TushareSource()

    if source.pro is None:
        logger.warning("Tushare未配置token，跳过测试")
        return None

    symbol = "000001.SZ"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    logger.info(f"获取 {symbol} 数据...")
    df = source.get_daily_price(symbol, start_date, end_date)
    logger.info(f"获取到 {len(df)} 条记录")

    if not df.empty:
        logger.info(f"\n最近5条数据:\n{df.tail()}")

    return df


def test_database():
    """测试数据库管理器"""
    logger.info("\n" + "=" * 50)
    logger.info("测试数据库管理器")
    logger.info("=" * 50)

    try:
        db = DatabaseManager()
        logger.info("数据库管理器初始化成功")

        # 创建表
        db.create_tables()
        logger.info("表结构检查/创建完成")

    except Exception as e:
        logger.warning(f"数据库测试失败: {e}")
        logger.info("请确保PostgreSQL已安装并配置正确")


def main():
    """主函数"""
    setup_logger()

    logger.info("QIS System 数据层测试")

    # 测试AKShare
    test_akshare()

    # 测试Tushare
    test_tushare()

    # 测试数据库
    test_database()

    logger.info("\n" + "=" * 50)
    logger.info("数据层测试完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

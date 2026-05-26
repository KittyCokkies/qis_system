"""
探索通联期货合约信息表
查找包含合约详细信息的表
"""
import sys
sys.path.insert(0, 'F:/qis_system')

from loguru import logger
import pymysql
from config import get_settings

logger.remove()
logger.add(sys.stdout, level="INFO")

def get_connection():
    """获取数据库连接"""
    settings = get_settings()
    config = settings.tonglian
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset=config.charset
    )

def search_tables_with_keyword(keyword):
    """搜索包含特定关键词的表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]

            # 过滤包含关键词的表
            matched = [t for t in tables if keyword.lower() in t.lower()]
            return matched
    finally:
        conn.close()

def describe_table(table_name):
    """描述表结构"""
    logger.info(f"\n=== 表: {table_name} ===")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()
            for col in columns:
                logger.info(f"  {col[0]}: {col[1]}")
            return [col[0] for col in columns]
    except Exception as e:
        logger.error(f"错误: {e}")
        return []
    finally:
        conn.close()

def sample_data(table_name, limit=3):
    """获取样本数据"""
    logger.info(f"\n样本数据 ({table_name}):")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            logger.info(f"列: {columns}")
            for row in rows:
                logger.info(f"  {row}")
    except Exception as e:
        logger.error(f"错误: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("搜索期货相关表...")

    # 搜索可能的表
    keywords = ['fut', 'contract', 'sec', 'instrument']
    all_tables = set()

    for kw in keywords:
        tables = search_tables_with_keyword(kw)
        logger.info(f"关键词 '{kw}': 找到 {len(tables)} 个表")
        all_tables.update(tables)

    logger.info(f"\n总共找到 {len(all_tables)} 个相关表")

    # 检查每个表的结构
    target_tables = [
        'futu',
        'sec_main',
        'sec_fut',
        'futu_stand_cont',
        'mkt_futd'
    ]

    for table in target_tables:
        if table in all_tables:
            columns = describe_table(table)

            # 检查是否包含我们需要的字段
            needed_fields = ['CONTRACT_MULTIPLIER', 'LIST_DATE', 'DELIST_DATE', 'TICK_SIZE']
            found = [f for f in needed_fields if any(f.lower() == c.lower() for c in columns)]

            if found:
                logger.info(f"  ✓ 包含字段: {found}")
                sample_data(table)
            else:
                logger.info(f"  ✗ 不包含需要的字段")

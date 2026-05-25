"""
Explore Tonglian database schema
"""
import sys
sys.path.insert(0, 'F:/qis_system')

from loguru import logger
import pymysql
from config import get_settings

# Setup logging
logger.remove()
logger.add(sys.stdout, level="INFO")

def get_connection():
    """Get database connection"""
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

def list_tables():
    """List all tables in database"""
    logger.info("=" * 50)
    logger.info("Listing all tables...")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]

            # Filter for relevant tables
            fut_tables = [t for t in tables if 'fut' in t.lower()]
            sec_tables = [t for t in tables if 'sec' in t.lower()]
            mkt_tables = [t for t in tables if 'mkt' in t.lower()]

            logger.info(f"Total tables: {len(tables)}")
            logger.info(f"Future-related tables: {fut_tables[:20]}")
            logger.info(f"Security-related tables: {sec_tables[:20]}")
            logger.info(f"Market data tables: {mkt_tables[:20]}")

            return tables
    finally:
        conn.close()

def describe_table(table_name):
    """Describe table structure"""
    logger.info("=" * 50)
    logger.info(f"Describing table: {table_name}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()

            for col in columns:
                logger.info(f"  {col[0]}: {col[1]}")

            return [col[0] for col in columns]
    except Exception as e:
        logger.error(f"Error: {e}")
        return []
    finally:
        conn.close()

def sample_data(table_name, limit=5):
    """Get sample data from table"""
    logger.info("=" * 50)
    logger.info(f"Sample data from {table_name}:")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            logger.info(f"Columns: {columns}")
            for row in rows:
                logger.info(f"  {row}")

            return columns, rows
    except Exception as e:
        logger.error(f"Error: {e}")
        return [], []
    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("Exploring Tonglian database schema...")

    # List all tables
    tables = list_tables()

    # Check specific tables
    target_tables = [
        'sec_fut_contracts',
        'mkt_futd',
        'sec_equity',
        'sec_main',
        'mkt_equd',
        'idx_cons',
        'md_calendar'
    ]

    for table in target_tables:
        if table in tables:
            describe_table(table)
            sample_data(table, 3)
        else:
            logger.warning(f"Table {table} not found")

    # Search for future-related tables with different names
    logger.info("=" * 50)
    logger.info("Searching for future-related tables...")
    for t in tables:
        if 'future' in t.lower() or 'fut' in t.lower():
            logger.info(f"Found: {t}")

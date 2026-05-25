"""
Test Tonglian data synchronization
"""
import sys
sys.path.insert(0, 'F:/qis_system')

from datetime import date, datetime
from loguru import logger

from data.tonglian_source import TonglianSource
from data.config.loader import AssetConfigLoader

# Setup logging
logger.remove()
logger.add(sys.stdout, level="INFO")

def test_connection():
    """Test database connection"""
    logger.info("=" * 50)
    logger.info("Testing Tonglian connection...")

    source = TonglianSource()
    result = source.test_connection()

    if result:
        logger.info("Connection test PASSED")
    else:
        logger.error("Connection test FAILED")
    return result

def test_future_contracts():
    """Test getting future contract info"""
    logger.info("=" * 50)
    logger.info("Testing future contracts query...")

    source = TonglianSource()

    # Test IF (沪深300股指期货)
    logger.info("Querying IF contracts...")
    df = source.get_future_contracts("IF", start_date=datetime(2024, 1, 1))

    if df.empty:
        logger.warning("No IF contracts found")
        return False

    logger.info(f"Found {len(df)} IF contracts")
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"First few records:\n{df.head()}")

    # Check required fields (note: multiplier not available in mkt_futd)
    required_fields = ['symbol', 'underlying', 'last_trade_date']
    missing = [f for f in required_fields if f not in df.columns]
    if missing:
        logger.error(f"Missing fields: {missing}")
        return False

    return True

def test_future_daily():
    """Test getting future daily price"""
    logger.info("=" * 50)
    logger.info("Testing future daily price query...")

    source = TonglianSource()

    # Test specific contract
    test_contract = "IF2501"  # IF 2025-01 contract
    logger.info(f"Querying daily data for {test_contract}...")

    df = source.get_future_daily(
        test_contract,
        start_date=datetime(2024, 12, 1),
        end_date=datetime(2024, 12, 31)
    )

    if df.empty:
        logger.warning(f"No daily data found for {test_contract}")
        return False

    logger.info(f"Found {len(df)} records for {test_contract}")
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"First few records:\n{df.head()}")

    # Check required fields (note: 'settle' is used instead of 'settlement')
    required_fields = ['symbol', 'date', 'open', 'high', 'low', 'close', 'settle', 'volume', 'open_interest']
    missing = [f for f in required_fields if f not in df.columns]
    if missing:
        logger.error(f"Missing fields: {missing}")
        return False

    return True

def test_get_contracts_by_date():
    """Test getting contracts by date"""
    logger.info("=" * 50)
    logger.info("Testing get contracts by date...")

    source = TonglianSource()

    # Test IF on a specific date
    test_date = datetime(2024, 12, 20)
    logger.info(f"Querying IF contracts for {test_date.date()}...")

    df = source.get_contracts_by_date("IF", test_date)

    if df.empty:
        logger.warning(f"No IF contracts found for {test_date.date()}")
        return False

    logger.info(f"Found {len(df)} IF contracts")
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"Data:\n{df[['symbol', 'date', 'close', 'settle', 'open_interest', 'expiry_date']].head()}")

    return True

def test_roll_configs():
    """Test loading roll configurations"""
    logger.info("=" * 50)
    logger.info("Testing roll configurations...")

    loader = AssetConfigLoader()
    configs = loader.get_active_roll_configs()

    logger.info(f"Found {len(configs)} active roll configs")

    # Show IF configs
    if_configs = [(uid, cfg) for uid, cfg in configs if uid == "IF"]
    logger.info(f"IF configs: {len(if_configs)}")

    for uid, cfg in if_configs[:3]:
        logger.info(f"  Config: {cfg.config_id}, type={cfg.roll_type}, start={cfg.roll_start_days}, end={cfg.roll_end_days}")

    return len(configs) > 0

if __name__ == "__main__":
    logger.info("Starting Tonglian sync tests...")
    logger.info(f"Current time: {datetime.now()}")

    results = []

    # Run tests
    results.append(("Connection", test_connection()))
    results.append(("Future Contracts", test_future_contracts()))
    results.append(("Future Daily", test_future_daily()))
    results.append(("Contracts By Date", test_get_contracts_by_date()))
    results.append(("Roll Configs", test_roll_configs()))

    # Summary
    logger.info("=" * 50)
    logger.info("Test Summary:")
    for name, result in results:
        status = "PASSED" if result else "FAILED"
        logger.info(f"  {name}: {status}")

    passed = sum(1 for _, r in results if r)
    total = len(results)
    logger.info(f"Total: {passed}/{total} tests passed")

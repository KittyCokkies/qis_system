#!/usr/bin/env python3
"""
Daily Data Synchronization Script (Manual Execution)

Usage:
    python scripts/sync_daily.py --date 2024-01-15 --source tonglian,wind
    python scripts/sync_daily.py --date 2024-01-15 --source bbg_excel --bbg-file data/bbg_input/bbg_data_20240115.xlsx
    python scripts/sync_daily.py --date 2024-01-15 --full-refresh
"""

import argparse
import sys
from pathlib import Path
from datetime import date, datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from data.sync.config_loader import SyncConfigLoader
from data.sync.tonglian_sync import TonglianSync
from data.sync.wind_sync import WindSync
from data.sync.bbg_excel_sync import BBGExcelSync
from data.sync.continuous_builder import ContinuousContractBuilder
from data.sync.concat_builder import ConcatBuilder


def init_logging():
    """Initialize logging"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )
    # Also log to file
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "sync_{time:YYYYMMDD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG"
    )


def parse_date(date_str: str) -> date:
    """Parse date string"""
    if date_str.lower() in ["today", "t"]:
        return date.today()
    if date_str.lower() in ["yesterday", "y"]:
        return date.today() - timedelta(days=1)
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def sync_tonglian(sync_date: date, full_refresh: bool = False):
    """Sync data from Tonglian"""
    logger.info(f"=" * 60)
    logger.info(f"Syncing Tonglian data for {sync_date}")
    logger.info(f"=" * 60)

    sync = TonglianSync()

    try:
        # Connect to source
        sync.connect()

        # Get active rollover configs
        configs = sync.get_active_configs()
        logger.info(f"Found {len(configs)} active rollover configs")

        # Sync each underlying
        for underlying, cfg in configs:
            try:
                logger.info(f"Syncing {underlying} ({cfg.config_id})...")
                count = sync.sync_daily_data(underlying, sync_date, full_refresh)
                logger.info(f"  - Imported {count} records")
            except Exception as e:
                logger.error(f"  - Failed to sync {underlying}: {e}")

        # Build continuous contracts
        logger.info("Building continuous contracts...")
        builder = ContinuousContractBuilder()
        for underlying, cfg in configs:
            try:
                builder.build_for_date(cfg.config_id, sync_date)
            except Exception as e:
                logger.error(f"  - Failed to build continuous for {cfg.config_id}: {e}")

        logger.info("Tonglian sync completed")

    except Exception as e:
        logger.error(f"Tonglian sync failed: {e}")
        raise
    finally:
        sync.disconnect()


def sync_wind(sync_date: date, full_refresh: bool = False):
    """Sync data from Wind"""
    logger.info(f"=" * 60)
    logger.info(f"Syncing Wind data for {sync_date}")
    logger.info(f"=" * 60)

    sync = WindSync()

    try:
        # Connect to source
        if not sync.connect():
            logger.error("Failed to connect to Wind")
            return

        # Sync indices
        indices = sync.get_active_indices()
        logger.info(f"Found {len(indices)} active indices")

        for idx in indices:
            try:
                logger.info(f"Syncing index {idx.symbol}...")
                count = sync.sync_index_daily(idx.symbol, sync_date, full_refresh)
                logger.info(f"  - Imported {count} records")
            except Exception as e:
                logger.error(f"  - Failed to sync {idx.symbol}: {e}")

        # Sync ETFs
        etfs = sync.get_active_etfs()
        logger.info(f"Found {len(etfs)} active ETFs")

        for etf in etfs:
            try:
                logger.info(f"Syncing ETF {etf.symbol}...")
                count = sync.sync_etf_daily(etf.symbol, sync_date, full_refresh)
                logger.info(f"  - Imported {count} records")
            except Exception as e:
                logger.error(f"  - Failed to sync {etf.symbol}: {e}")

        logger.info("Wind sync completed")

    except Exception as e:
        logger.error(f"Wind sync failed: {e}")
        raise
    finally:
        sync.disconnect()


def sync_bbg_excel(sync_date: date, file_path: Path, full_refresh: bool = False):
    """Sync data from Bloomberg Excel"""
    logger.info(f"=" * 60)
    logger.info(f"Syncing Bloomberg Excel data for {sync_date}")
    logger.info(f"File: {file_path}")
    logger.info(f"=" * 60)

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return

    sync = BBGExcelSync()

    try:
        # Load Excel file
        sync.load_file(file_path)

        # Get active indices from BBG
        indices = sync.get_active_indices()
        logger.info(f"Found {len(indices)} BBG indices in config")

        # Sync each sheet
        for idx in indices:
            try:
                logger.info(f"Syncing {idx.symbol}...")
                count = sync.sync_index_daily(idx.symbol, sync_date, full_refresh)
                logger.info(f"  - Imported {count} records")
            except Exception as e:
                logger.error(f"  - Failed to sync {idx.symbol}: {e}")

        logger.info("BBG Excel sync completed")

    except Exception as e:
        logger.error(f"BBG Excel sync failed: {e}")
        raise


def build_concat_assets(sync_date: date):
    """Build concat assets"""
    logger.info(f"=" * 60)
    logger.info(f"Building concat assets for {sync_date}")
    logger.info(f"=" * 60)

    builder = ConcatBuilder()

    try:
        assets = builder.get_active_assets()
        logger.info(f"Found {len(assets)} concat assets")

        for asset in assets:
            try:
                logger.info(f"Building {asset.symbol}...")
                count = builder.build_for_date(asset.symbol, sync_date)
                logger.info(f"  - Built {count} records")
            except Exception as e:
                logger.error(f"  - Failed to build {asset.symbol}: {e}")

        logger.info("Concat assets build completed")

    except Exception as e:
        logger.error(f"Concat build failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Daily Data Sync for QIS")
    parser.add_argument("--date", type=str, default="yesterday",
                        help="Sync date (YYYY-MM-DD, 'today', 'yesterday')")
    parser.add_argument("--source", type=str, default="all",
                        help="Data sources: all, tonglian, wind, bbg_excel")
    parser.add_argument("--bbg-file", type=str,
                        help="Bloomberg Excel file path")
    parser.add_argument("--full-refresh", action="store_true",
                        help="Delete and re-sync existing data")
    parser.add_argument("--skip-concat", action="store_true",
                        help="Skip building concat assets")

    args = parser.parse_args()

    init_logging()

    # Parse date
    try:
        sync_date = parse_date(args.date)
        logger.info(f"Sync date: {sync_date}")
    except ValueError as e:
        logger.error(f"Invalid date format: {args.date}")
        sys.exit(1)

    # Determine sources to sync
    sources = [s.strip() for s in args.source.split(",")]
    if "all" in sources:
        sources = ["tonglian", "wind", "bbg_excel"]

    # Sync each source
    success = True

    if "tonglian" in sources:
        try:
            sync_tonglian(sync_date, args.full_refresh)
        except Exception as e:
            logger.error(f"Tonglian sync failed: {e}")
            success = False

    if "wind" in sources:
        try:
            sync_wind(sync_date, args.full_refresh)
        except Exception as e:
            logger.error(f"Wind sync failed: {e}")
            success = False

    if "bbg_excel" in sources:
        if not args.bbg_file:
            logger.error("--bbg-file required for bbg_excel source")
            success = False
        else:
            try:
                sync_bbg_excel(sync_date, Path(args.bbg_file), args.full_refresh)
            except Exception as e:
                logger.error(f"BBG Excel sync failed: {e}")
                success = False

    # Build concat assets
    if not args.skip_concat:
        try:
            build_concat_assets(sync_date)
        except Exception as e:
            logger.error(f"Concat build failed: {e}")
            success = False

    # Summary
    logger.info(f"=" * 60)
    if success:
        logger.info("All sync tasks completed successfully!")
    else:
        logger.warning("Some sync tasks failed, check logs for details")
    logger.info(f"=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

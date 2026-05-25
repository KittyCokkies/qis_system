#!/usr/bin/env python3
"""
Historical Data Backfill Script

Usage:
    python scripts/sync_history.py --source tonglian --start 2020-01-01 --end 2024-01-15
    python scripts/sync_history.py --source wind --start 2020-01-01 --end 2024-01-15 --indices-only
    python scripts/sync_history.py --source tonglian --underlying RB,I,J --start 2020-01-01 --end 2024-01-15
"""

import argparse
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from tqdm import tqdm

from data.sync.tonglian_sync import TonglianSync
from data.sync.wind_sync import WindSync
from data.sync.continuous_builder import ContinuousContractBuilder


def init_logging():
    """Initialize logging"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "sync_history_{time:YYYYMMDD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG"
    )


def parse_date(date_str: str) -> date:
    """Parse date string"""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def get_trading_dates(start_date: date, end_date: date, exchange: str = "SSE") -> List[date]:
    """
    Get trading dates between start and end

    This is a simplified version - in production, should query trade_calendar table
    """
    dates = []
    current = start_date
    while current <= end_date:
        # Skip weekends (simplified)
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            dates.append(current)
        current += timedelta(days=1)
    return dates


def sync_tonglian_history(
    start_date: date,
    end_date: date,
    underlyings: List[str] = None,
    batch_size: int = 100
):
    """
    Sync historical data from Tonglian

    Args:
        start_date: Start date
        end_date: End date
        underlyings: List of underlyings to sync (None = all)
        batch_size: Number of days to process in each batch
    """
    logger.info("=" * 60)
    logger.info(f"Historical Sync: Tonglian")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info("=" * 60)

    sync = TonglianSync()
    builder = ContinuousContractBuilder()

    try:
        sync.connect()

        # Get configs to sync
        if underlyings:
            configs = []
            for u in underlyings:
                cfg = sync.get_configs_for_underlying(u)
                configs.extend(cfg)
        else:
            configs = sync.get_active_configs()

        logger.info(f"Will sync {len(configs)} configurations")

        # Get trading dates
        trading_dates = get_trading_dates(start_date, end_date)
        logger.info(f"Total trading dates: {len(trading_dates)}")

        # Sync each underlying
        for underlying, cfg in configs:
            logger.info(f"\nSyncing {underlying} ({cfg.config_id})...")

            total_records = 0
            error_count = 0

            # Process dates in batches with progress bar
            with tqdm(trading_dates, desc=f"{underlying}", unit="day") as pbar:
                for sync_date in pbar:
                    try:
                        count = sync.sync_daily_data(underlying, sync_date, full_refresh=False)
                        total_records += count
                        pbar.set_postfix({"records": total_records})
                    except Exception as e:
                        logger.debug(f"Error on {sync_date}: {e}")
                        error_count += 1

            logger.info(f"  Total records: {total_records}, Errors: {error_count}")

            # Build continuous contracts for this underlying
            logger.info(f"  Building continuous contracts...")
            try:
                builder.build_for_range(cfg.config_id, start_date, end_date)
                logger.info(f"  Continuous contracts built successfully")
            except Exception as e:
                logger.error(f"  Failed to build continuous: {e}")

        logger.info("\nTonglian historical sync completed!")

    except Exception as e:
        logger.error(f"Tonglian historical sync failed: {e}")
        raise
    finally:
        sync.disconnect()


def sync_wind_history(
    start_date: date,
    end_date: date,
    indices_only: bool = False,
    etfs_only: bool = False
):
    """
    Sync historical data from Wind

    Args:
        start_date: Start date
        end_date: End date
        indices_only: Only sync indices
        etfs_only: Only sync ETFs
    """
    logger.info("=" * 60)
    logger.info(f"Historical Sync: Wind")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info("=" * 60)

    sync = WindSync()

    try:
        if not sync.connect():
            logger.error("Failed to connect to Wind")
            return

        # Sync indices
        if not etfs_only:
            indices = sync.get_active_indices()
            logger.info(f"Syncing {len(indices)} indices...")

            for idx in tqdm(indices, desc="Indices"):
                try:
                    count = sync.sync_index_history(idx.symbol, start_date, end_date)
                    logger.info(f"  {idx.symbol}: {count} records")
                except Exception as e:
                    logger.error(f"  Failed to sync {idx.symbol}: {e}")

        # Sync ETFs
        if not indices_only:
            etfs = sync.get_active_etfs()
            logger.info(f"Syncing {len(etfs)} ETFs...")

            for etf in tqdm(etfs, desc="ETFs"):
                try:
                    count = sync.sync_etf_history(etf.symbol, start_date, end_date)
                    logger.info(f"  {etf.symbol}: {count} records")
                except Exception as e:
                    logger.error(f"  Failed to sync {etf.symbol}: {e}")

        logger.info("\nWind historical sync completed!")

    except Exception as e:
        logger.error(f"Wind historical sync failed: {e}")
        raise
    finally:
        sync.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Historical Data Backfill for QIS")
    parser.add_argument("--source", type=str, required=True,
                        choices=["tonglian", "wind"],
                        help="Data source")
    parser.add_argument("--start", type=str, required=True,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, required=True,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--underlying", type=str,
                        help="Comma-separated list of underlyings (tonglian only)")
    parser.add_argument("--indices-only", action="store_true",
                        help="Only sync indices (wind only)")
    parser.add_argument("--etfs-only", action="store_true",
                        help="Only sync ETFs (wind only)")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Batch size for processing")

    args = parser.parse_args()

    init_logging()

    # Parse dates
    try:
        start_date = parse_date(args.start)
        end_date = parse_date(args.end)
        if start_date > end_date:
            raise ValueError("Start date must be before end date")
        logger.info(f"Date range: {start_date} to {end_date}")
    except ValueError as e:
        logger.error(f"Invalid date: {e}")
        sys.exit(1)

    # Parse underlyings
    underlyings = None
    if args.underlying:
        underlyings = [u.strip() for u in args.underlying.split(",")]
        logger.info(f"Underlyings: {underlyings}")

    # Execute sync
    success = True

    if args.source == "tonglian":
        try:
            sync_tonglian_history(
                start_date,
                end_date,
                underlyings=underlyings,
                batch_size=args.batch_size
            )
        except Exception as e:
            logger.error(f"Tonglian sync failed: {e}")
            success = False

    elif args.source == "wind":
        try:
            sync_wind_history(
                start_date,
                end_date,
                indices_only=args.indices_only,
                etfs_only=args.etfs_only
            )
        except Exception as e:
            logger.error(f"Wind sync failed: {e}")
            success = False

    # Summary
    logger.info("=" * 60)
    if success:
        logger.info("Historical sync completed successfully!")
    else:
        logger.warning("Some sync tasks failed, check logs for details")
    logger.info("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

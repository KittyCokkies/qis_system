#!/usr/bin/env python3
"""
Import asset configuration to database

Usage:
    python scripts/import_config.py --config config/assets.yaml
    python scripts/import_config.py --validate  # Validate config without importing
    python scripts/import_config.py --reset     # Reset and reimport all configs
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import get_settings
from data.config.loader import AssetConfigLoader


def init_logging():
    """Initialize logging"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )


def get_db_connection():
    """Get database connection"""
    settings = get_settings()
    engine = create_engine(settings.database.url)
    return engine


def import_roll_configs(session, loader: AssetConfigLoader, reset: bool = False):
    """Import roll configurations to database"""
    configs = loader.get_all_roll_configs()

    if reset:
        logger.info("Clearing existing roll_configs...")
        session.execute(text("DELETE FROM roll_configs"))
        session.commit()

    imported_count = 0
    skipped_count = 0

    for underlying, cfg in configs:
        # Check if config already exists
        existing = session.execute(
            text("SELECT 1 FROM roll_configs WHERE config_id = :config_id"),
            {"config_id": cfg.config_id}
        ).fetchone()

        if existing and not reset:
            logger.debug(f"Config {cfg.config_id} already exists, skipping")
            skipped_count += 1
            continue

        # Insert new config
        session.execute(
            text("""
                INSERT INTO roll_configs (
                    config_id, underlying, config_name, roll_type, price_type,
                    roll_start_days, roll_end_days, roll_window, threshold,
                    condition_type, transaction_cost, lead_months, start_date,
                    data_source, update_flag, is_active
                ) VALUES (
                    :config_id, :underlying, :config_name, :roll_type, :price_type,
                    :roll_start_days, :roll_end_days, :roll_window, :threshold,
                    :condition_type, :transaction_cost, :lead_months, :start_date,
                    :data_source, :update_flag, :is_active
                )
                ON CONFLICT (config_id) DO UPDATE SET
                    underlying = EXCLUDED.underlying,
                    config_name = EXCLUDED.config_name,
                    roll_type = EXCLUDED.roll_type,
                    price_type = EXCLUDED.price_type,
                    roll_start_days = EXCLUDED.roll_start_days,
                    roll_end_days = EXCLUDED.roll_end_days,
                    roll_window = EXCLUDED.roll_window,
                    threshold = EXCLUDED.threshold,
                    condition_type = EXCLUDED.condition_type,
                    transaction_cost = EXCLUDED.transaction_cost,
                    lead_months = EXCLUDED.lead_months,
                    start_date = EXCLUDED.start_date,
                    data_source = EXCLUDED.data_source,
                    update_flag = EXCLUDED.update_flag,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "config_id": cfg.config_id,
                "underlying": underlying,
                "config_name": cfg.config_name,
                "roll_type": cfg.roll_type.value,
                "price_type": cfg.price_type.value,
                "roll_start_days": cfg.roll_start_days,
                "roll_end_days": cfg.roll_end_days,
                "roll_window": cfg.roll_window,
                "threshold": cfg.threshold,
                "condition_type": cfg.condition_type.value if cfg.condition_type else None,
                "transaction_cost": cfg.transaction_cost,
                "lead_months": cfg.lead_months,
                "start_date": cfg.start_date,
                "data_source": cfg.data_source,
                "update_flag": cfg.update_flag,
                "is_active": True,
            }
        )
        imported_count += 1
        logger.debug(f"Imported config: {cfg.config_id}")

    session.commit()
    logger.info(f"Imported {imported_count} roll configs, skipped {skipped_count}")
    return imported_count, skipped_count


def import_concat_configs(session, loader: AssetConfigLoader, reset: bool = False):
    """Import concat asset configurations to database"""
    concat_assets = loader.get_all_concat_assets()

    if reset:
        logger.info("Clearing existing concat_asset_configs...")
        session.execute(text("DELETE FROM concat_asset_configs"))
        session.commit()

    imported_count = 0
    skipped_count = 0

    import json

    for asset in concat_assets:
        # Check if already exists
        existing = session.execute(
            text("SELECT 1 FROM concat_asset_configs WHERE symbol = :symbol"),
            {"symbol": asset.symbol}
        ).fetchone()

        if existing and not reset:
            logger.debug(f"Concat asset {asset.symbol} already exists, skipping")
            skipped_count += 1
            continue

        # Convert components to JSON
        components = []
        for comp in asset.components:
            components.append({
                "symbol": comp.symbol,
                "start_date": comp.start_date.isoformat() if comp.start_date else None,
                "end_date": comp.end_date.isoformat() if comp.end_date else None,
            })

        session.execute(
            text("""
                INSERT INTO concat_asset_configs (
                    symbol, name, description, asset_type, components, update_flag, is_active
                ) VALUES (
                    :symbol, :name, :description, :asset_type, :components, :update_flag, :is_active
                )
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    asset_type = EXCLUDED.asset_type,
                    components = EXCLUDED.components,
                    update_flag = EXCLUDED.update_flag,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "description": asset.description,
                "asset_type": asset.type,
                "components": json.dumps(components),
                "update_flag": asset.update_flag,
                "is_active": True,
            }
        )
        imported_count += 1
        logger.debug(f"Imported concat asset: {asset.symbol}")

    session.commit()
    logger.info(f"Imported {imported_count} concat assets, skipped {skipped_count}")
    return imported_count, skipped_count


def validate_config(loader: AssetConfigLoader) -> bool:
    """Validate configuration"""
    logger.info("Validating configuration...")
    is_valid = True

    # Check for duplicate config_ids
    config_ids = {}
    for underlying, future in loader.futures.items():
        for cfg in future.configs:
            if cfg.config_id in config_ids:
                logger.error(f"Duplicate config_id: {cfg.config_id}")
                is_valid = False
            else:
                config_ids[cfg.config_id] = underlying

    # Check config_id format
    for config_id in config_ids.keys():
        try:
            # Basic format check
            parts = config_id.split("_")
            if len(parts) < 3:
                logger.error(f"Invalid config_id format (too few parts): {config_id}")
                is_valid = False
                continue

            underlying = parts[0]
            type_pq = parts[1]
            price = parts[2]

            # Check type (S or D)
            if not (type_pq.startswith("S") or type_pq.startswith("D")):
                logger.error(f"Invalid roll type in config_id: {config_id}")
                is_valid = False

            # Check price type
            if price not in ["settle", "close"]:
                logger.error(f"Invalid price type in config_id: {config_id}")
                is_valid = False

        except Exception as e:
            logger.error(f"Error validating config_id {config_id}: {e}")
            is_valid = False

    # Print statistics
    if is_valid:
        logger.info("Configuration validation passed!")
        loader.print_statistics()
    else:
        logger.error("Configuration validation failed!")

    return is_valid


def main():
    parser = argparse.ArgumentParser(description="Import asset configuration to database")
    parser.add_argument("--config", type=str, default="config/assets.yaml",
                        help="Path to config file")
    parser.add_argument("--validate", action="store_true",
                        help="Validate config only, do not import")
    parser.add_argument("--reset", action="store_true",
                        help="Reset and reimport all configs")
    parser.add_argument("--skip-roll", action="store_true",
                        help="Skip importing roll configs")
    parser.add_argument("--skip-concat", action="store_true",
                        help="Skip importing concat configs")

    args = parser.parse_args()

    init_logging()

    # Load configuration
    logger.info(f"Loading configuration from {args.config}...")
    try:
        loader = AssetConfigLoader(args.config).load()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate
    if not validate_config(loader):
        if args.validate:
            sys.exit(1)
        else:
            logger.warning("Validation failed but continuing with import...")

    if args.validate:
        logger.info("Validation complete, exiting")
        sys.exit(0)

    # Connect to database
    logger.info("Connecting to database...")
    try:
        engine = get_db_connection()
        Session = sessionmaker(bind=engine)
        session = Session()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    # Import configurations
    try:
        if not args.skip_roll:
            logger.info("Importing roll configurations...")
            import_roll_configs(session, loader, reset=args.reset)

        if not args.skip_concat:
            logger.info("Importing concat asset configurations...")
            import_concat_configs(session, loader, reset=args.reset)

        logger.info("Import completed successfully!")

    except Exception as e:
        logger.error(f"Import failed: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()

"""
Tonglian Data Synchronization

Syncs futures data from Tonglian MySQL database.
"""

from datetime import date
from typing import List, Tuple, Optional
import pandas as pd
from loguru import logger

from data.tonglian_source import TonglianSource
from data.config.loader import AssetConfigLoader, RollConfig
from data.database import DatabaseManager


class TonglianSync:
    """Tonglian data synchronizer"""

    def __init__(self):
        self.source = TonglianSource()
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._connected = False

    def connect(self) -> bool:
        """Connect to data source"""
        try:
            self.source.connect()
            self._connected = True
            logger.info("Connected to Tonglian")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Tonglian: {e}")
            return False

    def disconnect(self):
        """Disconnect from source"""
        if self._connected:
            self.source.close()
            self._connected = False
            logger.info("Disconnected from Tonglian")

    def get_active_configs(self) -> List[Tuple[str, RollConfig]]:
        """Get all active roll configurations"""
        return self.config_loader.get_active_roll_configs()

    def get_configs_for_underlying(self, underlying: str) -> List[Tuple[str, RollConfig]]:
        """Get configs for specific underlying"""
        future = self.config_loader.get_future(underlying)
        if future:
            return [(underlying, cfg) for cfg in future.get_active_configs()]
        return []

    def sync_daily_data(self, underlying: str, sync_date: date, full_refresh: bool = False) -> int:
        """
        Sync daily data for an underlying

        Args:
            underlying: Underlying code (e.g., 'RB', 'IF')
            sync_date: Date to sync
            full_refresh: If True, delete existing data first

        Returns:
            Number of records imported
        """
        # Get future config
        future = self.config_loader.get_future(underlying)
        if not future:
            raise ValueError(f"Unknown underlying: {underlying}")

        # Query Tonglian for all contracts of this underlying on this date
        # This is a placeholder - actual implementation depends on Tonglian schema
        query = """
            SELECT
                symbol,
                trade_date as date,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                settle_price as settle,
                volume,
                amount,
                open_interest
            FROM CMPT_FutureDailyPrice
            WHERE underlying = %s AND trade_date = %s
        """

        try:
            df = self.source.raw_query(query, (underlying, sync_date))
        except Exception as e:
            logger.error(f"Failed to query Tonglian: {e}")
            # Return 0 for now - in production should handle this better
            return 0

        if df.empty:
            logger.debug(f"No data for {underlying} on {sync_date}")
            return 0

        # Insert into database
        if full_refresh:
            # Delete existing data first
            self.db.execute(
                "DELETE FROM prices_future WHERE underlying = %s AND date = %s",
                (underlying, sync_date)
            )

        # Insert data
        records = df.to_dict('records')
        for record in records:
            self.db.execute("""
                INSERT INTO prices_future
                (symbol, underlying, date, open, high, low, close, settle,
                 volume, amount, open_interest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    settle = EXCLUDED.settle,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    open_interest = EXCLUDED.open_interest
            """, (
                record['symbol'], underlying, sync_date,
                record['open'], record['high'], record['low'],
                record['close'], record['settle'],
                record['volume'], record['amount'], record['open_interest']
            ))

        logger.debug(f"Imported {len(records)} records for {underlying} on {sync_date}")
        return len(records)

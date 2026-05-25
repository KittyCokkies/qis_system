"""
Wind Data Synchronization

Syncs index and ETF data from Wind.
"""

from datetime import date
from typing import List
from loguru import logger

from data.wind_source import WindSource
from data.config.loader import AssetConfigLoader, IndexAsset, ETFAsset
from data.database import DatabaseManager


class WindSync:
    """Wind data synchronizer"""

    def __init__(self):
        self.source = WindSource()
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._connected = False

    def connect(self) -> bool:
        """Connect to Wind"""
        try:
            self.source.connect()
            self._connected = True
            logger.info("Connected to Wind")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Wind: {e}")
            return False

    def disconnect(self):
        """Disconnect from Wind"""
        if self._connected:
            self.source.close()
            self._connected = False
            logger.info("Disconnected from Wind")

    def get_active_indices(self) -> List[IndexAsset]:
        """Get active indices from config"""
        return [idx for idx in self.config_loader.get_all_indices() if idx.update_flag == 1]

    def get_active_etfs(self) -> List[ETFAsset]:
        """Get active ETFs from config"""
        return [etf for etf in self.config_loader.get_all_etfs() if etf.update_flag == 1]

    def sync_index_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """Sync daily data for an index"""
        if not self._connected:
            raise RuntimeError("Not connected to Wind")

        try:
            # Use Wind API to get daily data
            df = self.source.get_daily_price(symbol, sync_date, sync_date)

            if df.empty:
                logger.debug(f"No data for {symbol} on {sync_date}")
                return 0

            # Insert to database
            record = df.iloc[0].to_dict()

            if full_refresh:
                self.db.execute(
                    "DELETE FROM prices_index WHERE symbol = %s AND date = %s",
                    (symbol, sync_date)
                )

            self.db.execute("""
                INSERT INTO prices_index
                (symbol, date, open, high, low, close, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount
            """, (
                symbol, sync_date,
                record.get('open'), record.get('high'),
                record.get('low'), record.get('close'),
                record.get('volume'), record.get('amount')
            ))

            return 1

        except Exception as e:
            logger.error(f"Failed to sync {symbol}: {e}")
            return 0

    def sync_etf_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """Sync daily data for an ETF (treated as stock)"""
        # ETFs are synced similarly to indices but stored in prices_stock
        # Implementation placeholder
        return 0

    def sync_index_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """Sync historical data for an index"""
        if not self._connected:
            raise RuntimeError("Not connected to Wind")

        try:
            df = self.source.get_daily_price(symbol, start_date, end_date)

            if df.empty:
                logger.warning(f"No data for {symbol} from {start_date} to {end_date}")
                return 0

            # Batch insert
            records = df.reset_index().to_dict('records')
            for record in records:
                self.db.execute("""
                    INSERT INTO prices_index
                    (symbol, date, open, high, low, close, volume, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        amount = EXCLUDED.amount
                """, (
                    symbol, record.get('date'),
                    record.get('open'), record.get('high'),
                    record.get('low'), record.get('close'),
                    record.get('volume'), record.get('amount')
                ))

            return len(records)

        except Exception as e:
            logger.error(f"Failed to sync {symbol} history: {e}")
            return 0

    def sync_etf_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """Sync historical data for an ETF"""
        # Implementation placeholder
        return 0

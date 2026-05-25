"""
Bloomberg Excel Data Synchronization

Reads Bloomberg data from Excel files.

Expected format:
    File: bbg_data_YYYYMMDD.xlsx
    Sheets: Each sheet named after a Bloomberg ticker (e.g., 'SPX Index', 'USGG10YR Index')
    Columns: date (YYYY-MM-DD), nav (numeric)
"""

from datetime import date
from pathlib import Path
from typing import List, Optional
import pandas as pd
from loguru import logger

from data.config.loader import AssetConfigLoader, IndexAsset
from data.database import DatabaseManager


class BBGExcelSync:
    """Bloomberg Excel data synchronizer"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._file_path: Optional[Path] = None
        self._data: dict = {}  # sheet_name -> DataFrame

    def load_file(self, file_path: Path) -> bool:
        """
        Load Excel file

        Args:
            file_path: Path to Excel file

        Returns:
            True if successful
        """
        try:
            self._file_path = Path(file_path)

            # Read all sheets
            xl = pd.ExcelFile(self._file_path)

            for sheet_name in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet_name)

                # Validate columns
                if 'date' not in df.columns or 'nav' not in df.columns:
                    logger.warning(f"Sheet {sheet_name}: Missing required columns (date, nav)")
                    continue

                # Convert date column
                df['date'] = pd.to_datetime(df['date']).dt.date

                self._data[sheet_name] = df
                logger.debug(f"Loaded {len(df)} records from sheet {sheet_name}")

            logger.info(f"Loaded {len(self._data)} sheets from {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Excel file: {e}")
            return False

    def get_active_indices(self) -> List[IndexAsset]:
        """Get BBG indices from config"""
        return self.config_loader.get_indices_by_source("bbg_excel")

    def sync_index_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """
        Sync daily data for an index

        The symbol should match the sheet name in the Excel file.
        Common BBG tickers: 'SPX Index', 'NDX Index', 'SX5E Index', etc.
        """
        if not self._data:
            raise RuntimeError("No Excel file loaded")

        # Find matching sheet (handle variations in naming)
        sheet_name = None
        for name in self._data.keys():
            if symbol in name or name in symbol:
                sheet_name = name
                break

        if sheet_name is None:
            logger.warning(f"No sheet found for symbol {symbol}")
            return 0

        df = self._data[sheet_name]

        # Filter for sync_date
        day_data = df[df['date'] == sync_date]

        if day_data.empty:
            logger.debug(f"No data for {symbol} on {sync_date}")
            return 0

        record = day_data.iloc[0]

        if full_refresh:
            self.db.execute(
                "DELETE FROM prices_index WHERE symbol = %s AND date = %s",
                (symbol, sync_date)
            )

        self.db.execute("""
            INSERT INTO prices_index
            (symbol, date, close, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                close = EXCLUDED.close,
                source = EXCLUDED.source
        """, (
            symbol, sync_date, record['nav'], 'bbg_excel'
        ))

        logger.debug(f"Imported {symbol} for {sync_date}: {record['nav']}")
        return 1

    def sync_index_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """Sync historical data for an index"""
        if not self._data:
            raise RuntimeError("No Excel file loaded")

        sheet_name = None
        for name in self._data.keys():
            if symbol in name or name in symbol:
                sheet_name = name
                break

        if sheet_name is None:
            logger.warning(f"No sheet found for symbol {symbol}")
            return 0

        df = self._data[sheet_name]

        # Filter date range
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        range_data = df[mask]

        if range_data.empty:
            logger.warning(f"No data for {symbol} from {start_date} to {end_date}")
            return 0

        records = range_data.to_dict('records')
        for record in records:
            self.db.execute("""
                INSERT INTO prices_index
                (symbol, date, close, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    close = EXCLUDED.close,
                    source = EXCLUDED.source
            """, (
                symbol, record['date'], record['nav'], 'bbg_excel'
            ))

        return len(records)

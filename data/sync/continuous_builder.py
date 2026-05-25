"""
Continuous Contract Builder

Builds continuous price series from individual futures contracts
based on roll configurations.
"""

from datetime import date, timedelta
from typing import Optional, List
from loguru import logger

from data.config.loader import AssetConfigLoader
from data.config.models import RollConfig, RolloverType, PriceType
from data.database import DatabaseManager
from data.future_roll import FutureRollAnalyzer


class ContinuousContractBuilder:
    """Builds continuous contract price series"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self.roll_analyzer = FutureRolloverAnalyzer()

    def build_for_date(self, config_id: str, build_date: date) -> int:
        """
        Build continuous contract for a specific date

        Args:
            config_id: Rollover config ID (e.g., 'IF_S7q4_settle')
            build_date: Date to build

        Returns:
            Number of records created (0 or 1)
        """
        # Get config
        config = self.config_loader.get_roll_config(config_id)
        if not config:
            raise ValueError(f"Unknown config_id: {config_id}")

        # Get underlying
        underlying = config_id.split('_')[0]

        # Get all contracts for this underlying on this date
        contracts = self._get_contracts_for_date(underlying, build_date)

        if not contracts:
            logger.debug(f"No contracts found for {underlying} on {build_date}")
            return 0

        # Determine current and next contracts based on roll rules
        current_contract, next_contract, days_to_expiry = self._determine_contracts(
            underlying, contracts, build_date, config
        )

        if not current_contract:
            logger.debug(f"Could not determine current contract for {underlying} on {build_date}")
            return 0

        # Get prices
        current_price = self._get_contract_price(current_contract, build_date, config.price_type)
        next_price = None
        if next_contract:
            next_price = self._get_contract_price(next_contract, build_date, config.price_type)

        # Calculate continuous price and roll info
        continuous_price = current_price
        price_diff = None
        roll_return = None
        is_roll_day = False
        roll_type = 'hold'

        if next_contract and next_price:
            price_diff = next_price - current_price if next_price and current_price else None

            # Check if roll should occur
            if days_to_expiry is not None:
                if days_to_expiry <= config.roll_end_days:
                    # Forced roll
                    is_roll_day = True
                    roll_type = 'forced_roll'
                elif days_to_expiry <= config.roll_start_days:
                    # Observation window - check dynamic conditions if applicable
                    if config.roll_type == RolloverType.DYNAMIC:
                        if self._should_roll_dynamic(underlying, current_contract, next_contract, build_date, config):
                            is_roll_day = True
                            roll_type = 'observation_roll'

        # Insert continuous price record
        self.db.execute("""
            INSERT INTO prices_future_continuous (
                config_id, underlying, date,
                current_contract, next_contract,
                current_price, next_price, continuous_price,
                price_diff, roll_return, days_to_expiry,
                is_roll_day, roll_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (config_id, date) DO UPDATE SET
                current_contract = EXCLUDED.current_contract,
                next_contract = EXCLUDED.next_contract,
                current_price = EXCLUDED.current_price,
                next_price = EXCLUDED.next_price,
                continuous_price = EXCLUDED.continuous_price,
                price_diff = EXCLUDED.price_diff,
                roll_return = EXCLUDED.roll_return,
                days_to_expiry = EXCLUDED.days_to_expiry,
                is_roll_day = EXCLUDED.is_roll_day,
                roll_type = EXCLUDED.roll_type
        """, (
            config_id, underlying, build_date,
            current_contract, next_contract,
            current_price, next_price, continuous_price,
            price_diff, roll_return, days_to_expiry,
            is_roll_day, roll_type
        ))

        logger.debug(f"Built continuous price for {config_id} on {build_date}: {continuous_price}")
        return 1

    def build_for_range(self, config_id: str, start_date: date, end_date: date) -> int:
        """
        Build continuous contracts for a date range

        Args:
            config_id: Rollover config ID
            start_date: Start date
            end_date: End date

        Returns:
            Number of records created
        """
        count = 0
        current = start_date
        while current <= end_date:
            try:
                if self.build_for_date(config_id, current) > 0:
                    count += 1
            except Exception as e:
                logger.error(f"Failed to build {config_id} for {current}: {e}")
            current += timedelta(days=1)

        logger.info(f"Built {count} continuous price records for {config_id}")
        return count

    def _get_contracts_for_date(self, underlying: str, query_date: date) -> List[str]:
        """Get all available contract codes for an underlying on a date"""
        result = self.db.execute("""
            SELECT DISTINCT symbol FROM prices_future
            WHERE underlying = %s AND date = %s
            ORDER BY symbol
        """, (underlying, query_date))

        return [row[0] for row in result.fetchall()]

    def _get_contract_price(self, symbol: str, query_date: date, price_type: PriceType) -> Optional[float]:
        """Get contract price (settle or close)"""
        price_col = 'settle' if price_type == PriceType.SETTLE else 'close'

        result = self.db.execute(f"""
            SELECT {price_col} FROM prices_future
            WHERE symbol = %s AND date = %s
        """, (symbol, query_date))

        row = result.fetchone()
        return row[0] if row else None

    def _determine_contracts(
        self,
        underlying: str,
        contracts: List[str],
        query_date: date,
        config: RollConfig
    ) -> tuple:
        """
        Determine current and next contracts

        Returns:
            (current_contract, next_contract, days_to_expiry)
        """
        if not contracts:
            return None, None, None

        # Parse contracts to get expiry dates
        future = self.config_loader.get_future(underlying)
        contract_expiries = []

        for contract in contracts:
            try:
                _, year, month = future.parse_contract_code(contract)
                # Simplified: Assume expiry is last Friday of month
                # In production, should use actual expiry calendar
                expiry = self._get_last_friday(year, month)
                days_to_exp = (expiry - query_date).days
                contract_expiries.append((contract, expiry, days_to_exp))
            except ValueError:
                logger.warning(f"Could not parse contract code: {contract}")
                continue

        if not contract_expiries:
            return None, None, None

        # Sort by expiry
        contract_expiries.sort(key=lambda x: x[1])

        # Current contract is the one with largest OI (simplified)
        # In production, should query actual OI data
        # For now, use the first contract that hasn't expired
        current = None
        next_contract = None
        days_to_expiry = None

        for i, (contract, expiry, days) in enumerate(contract_expiries):
            if days >= 0:  # Not expired
                if current is None:
                    current = contract
                    days_to_expiry = days
                    # Next contract is the one after current
                    if i + 1 < len(contract_expiries):
                        next_contract = contract_expiries[i + 1][0]
                break

        return current, next_contract, days_to_expiry

    def _should_roll_dynamic(
        self,
        underlying: str,
        current_contract: str,
        next_contract: str,
        query_date: date,
        config: RollConfig
    ) -> bool:
        """
        Check if should roll based on dynamic conditions

        For OI-driven: roll when next contract OI > current contract OI * threshold
        For volume-driven: roll when next contract volume > current contract volume * threshold
        """
        # Get OI or volume for both contracts
        metric = 'open_interest' if config.condition_type != 'volume' else 'volume'

        result = self.db.execute(f"""
            SELECT symbol, {metric} FROM prices_future
            WHERE symbol IN (%s, %s) AND date = %s
        """, (current_contract, next_contract, query_date))

        data = {row[0]: row[1] for row in result.fetchall()}

        if current_contract not in data or next_contract not in data:
            return False

        current_metric = data[current_contract]
        next_metric = data[next_contract]

        if not current_metric or not next_metric:
            return False

        threshold = config.threshold or 1.0

        return next_metric > current_metric * threshold

    @staticmethod
    def _get_last_friday(year: int, month: int) -> date:
        """Get the last Friday of a month (simplified expiry rule)"""
        import calendar

        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        # Find last Friday (Friday = 4)
        while last_date.weekday() != 4:
            last_date -= timedelta(days=1)

        return last_date

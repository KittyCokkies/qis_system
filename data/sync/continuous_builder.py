"""
Continuous Contract Builder

根据展期配置从期货原始合约构建连续价格序列
支持静态和动态展期规则，处理双窗口展期逻辑
"""

from datetime import date, timedelta
from typing import Optional, List
from loguru import logger

from data.config.loader import AssetConfigLoader
from data.config.models import RolloverConfig, RollType, PriceType
from data.database import DatabaseManager
from data.future_roll import FutureRollAnalyzer


class ContinuousContractBuilder:
    """连续合约构建器

    基于展期配置，将多个期货原始合约拼接成一条连续的价格序列
    消除换月跳空，支持不同展期规则和价格类型

    Attributes:
        db: 数据库管理器
        config_loader: 资产配置加载器
        roll_analyzer: 展期分析器

    Example:
        >>> builder = ContinuousContractBuilder()
        >>> # 构建单日连续合约
        >>> builder.build_for_date('IF_S7q4_settle', date(2024, 1, 15))
        >>> # 构建一段时间
        >>> builder.build_for_range('IF_S7q4_settle', date(2024, 1, 1), date(2024, 12, 31))
    """

    def __init__(self):
        """初始化构建器"""
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self.roll_analyzer = FutureRollAnalyzer()

    def build_for_date(self, config_id: str, build_date: date) -> int:
        """
        为特定日期构建连续合约

        根据展期配置，确定当日应持有的合约，计算连续价格

        Args:
            config_id: 展期配置ID (例如: 'IF_S7q4_settle')
            build_date: 构建日期

        Returns:
            int: 创建的记录数 (0 或 1)

        Raises:
            ValueError: 如果 config_id 不存在
        """
        # 获取配置
        config = self.config_loader.get_roll_config(config_id)
        if not config:
            raise ValueError(f"Unknown config_id: {config_id}")

        # 从 config_id 解析出品种代码
        underlying = config_id.split('_')[0]

        # 获取该品种在该日期的所有合约
        contracts = self._get_contracts_for_date(underlying, build_date)

        if not contracts:
            logger.debug(f"No contracts found for {underlying} on {build_date}")
            return 0

        # 根据展期规则确定当前和下一合约
        current_contract, next_contract, days_to_expiry = self._determine_contracts(
            underlying, contracts, build_date, config
        )

        if not current_contract:
            logger.debug(f"Could not determine current contract for {underlying} on {build_date}")
            return 0

        # 获取价格
        current_price = self._get_contract_price(current_contract, build_date, config.price_type)
        next_price = None
        if next_contract:
            next_price = self._get_contract_price(next_contract, build_date, config.price_type)

        # 计算连续价格和展期信息
        continuous_price = current_price
        price_diff = None
        roll_return = None
        is_roll_day = False
        roll_type = 'hold'

        if next_contract and next_price:
            price_diff = next_price - current_price if next_price and current_price else None

            # 检查是否应该展期
            if days_to_expiry is not None:
                if days_to_expiry <= config.roll_end_days:
                    # 强制展期
                    is_roll_day = True
                    roll_type = 'forced_roll'
                elif days_to_expiry <= config.roll_start_days:
                    # 观察窗口 - 如果是动态展期则检查条件
                    if config.roll_type == RollType.DYNAMIC:
                        if self._should_roll_dynamic(underlying, current_contract, next_contract, build_date, config):
                            is_roll_day = True
                            roll_type = 'observation_roll'

        # 插入连续价格记录
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
        为日期范围构建连续合约

        批量构建一段时间内的连续合约价格

        Args:
            config_id: 展期配置ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            int: 创建的记录总数
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
        """获取某一日期某品种的所有可用合约代码"""
        result = self.db.execute("""
            SELECT DISTINCT symbol FROM prices_future
            WHERE underlying = %s AND date = %s
            ORDER BY symbol
        """, (underlying, query_date))

        return [row[0] for row in result.fetchall()]

    def _get_contract_price(self, symbol: str, query_date: date, price_type: PriceType) -> Optional[float]:
        """获取合约价格 (结算价或收盘价)"""
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
        config: RolloverConfig
    ) -> tuple:
        """
        确定当前合约和下一合约

        Returns:
            (current_contract, next_contract, days_to_expiry)
        """
        if not contracts:
            return None, None, None

        # 解析合约获取到期日
        future = self.config_loader.get_future(underlying)
        contract_expiries = []

        for contract in contracts:
            try:
                _, year, month = future.parse_contract_code(contract)
                # 简化: 假设到期日是当月最后一个周五
                # 生产环境应该使用实际到期日历
                expiry = self._get_last_friday(year, month)
                days_to_exp = (expiry - query_date).days
                contract_expiries.append((contract, expiry, days_to_exp))
            except ValueError:
                logger.warning(f"Could not parse contract code: {contract}")
                continue

        if not contract_expiries:
            return None, None, None

        # 按到期日排序
        contract_expiries.sort(key=lambda x: x[1])

        # 当前合约是持仓量最大的 (简化)
        # 生产环境应该查询实际持仓量数据
        # 现在使用第一个未过期的合约
        current = None
        next_contract = None
        days_to_expiry = None

        for i, (contract, expiry, days) in enumerate(contract_expiries):
            if days >= 0:  # 未过期
                if current is None:
                    current = contract
                    days_to_expiry = days
                    # 下一合约是当前合约之后的那个
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
        config: RolloverConfig
    ) -> bool:
        """
        根据动态条件检查是否应该展期

        对于持仓量驱动: 当下一合约持仓量 > 当前合约持仓量 * 阈值时展期
        对于成交量驱动: 当下一合约成交量 > 当前合约成交量 * 阈值时展期
        """
        # 获取两个合约的持仓量或成交量
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
        """获取某月最后一个周五 (简化版到期日规则)"""
        import calendar

        # 获取当月最后一天
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        # 找到最后一个周五 (周五 = 4)
        while last_date.weekday() != 4:
            last_date -= timedelta(days=1)

        return last_date

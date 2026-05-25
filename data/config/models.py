"""
Asset Configuration Data Models

Defines dataclasses for asset configuration including futures, indices, ETFs, and concat assets.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from enum import Enum
import re


class Exchange(Enum):
    """交易所枚举"""
    SHFE = "SHFE"      # 上期所
    DCE = "DCE"        # 大商所
    ZCE = "ZCE"        # 郑商所
    CFFEX = "CFFEX"    # 中金所
    INE = "INE"        # 能源中心
    SSE = "SSE"        # 上交所
    SZSE = "SZSE"      # 深交所
    BSE = "BSE"        # 北交所
    HKEX = "HKEX"      # 港交所
    CME = "CME"        # 芝加哥商业交易所
    CBT = "CBT"        # 芝加哥期货交易所
    EUREX = "EUREX"    # 欧洲期货交易所
    OSE = "OSE"        # 大阪证券交易所
    COMEX = "COMEX"    # 纽约商品交易所
    NYMEX = "NYMEX"    # 纽约商业交易所
    IPE = "IPE"        # 洲际交易所


class RolloverType(Enum):
    """展期类型"""
    STATIC = "static"
    DYNAMIC = "dynamic"


class PriceType(Enum):
    """价格类型"""
    SETTLE = "settle"
    CLOSE = "close"


class ConditionType(Enum):
    """动态展期条件类型"""
    OPEN_INTEREST = "open_interest"
    VOLUME = "volume"


class AssetClass(Enum):
    """资产类别"""
    FUTURE = "future"
    FUTURE_CONTINUOUS = "future_continuous"
    INDEX = "index"
    ETF = "etf"
    STOCK = "stock"
    BOND = "bond"
    CONCAT = "concat"


@dataclass
class RolloverConfig:
    """展期配置"""
    config_id: str                    # 配置唯一ID，如 "IF_S7q4_settle"
    config_name: str                  # 配置名称
    rollover_type: RolloverType      # static / dynamic
    price_type: PriceType            # settle / close
    roll_start_days: int             # p: 到期前p天开始观察
    roll_end_days: int               # q: 到期前q天强制展期
    roll_window: int = 3             # 展期窗口天数
    threshold: Optional[float] = None # th: 切换阈值
    condition_type: Optional[ConditionType] = None  # 动态展期条件
    transaction_cost: float = 0.0     # 交易成本
    lead_months: Optional[str] = None # 合约月份序列，如 "1,5,9"
    start_date: Optional[date] = None # 数据开始日期
    data_source: str = "tonglian"     # 数据源
    update_flag: int = 1              # 是否更新

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.rollover_type, str):
            self.rollover_type = RolloverType(self.rollover_type)
        if isinstance(self.price_type, str):
            self.price_type = PriceType(self.price_type)
        if isinstance(self.condition_type, str):
            self.condition_type = ConditionType(self.condition_type)
        if isinstance(self.start_date, str):
            self.start_date = datetime.strptime(self.start_date, "%Y-%m-%d").date()

    @property
    def is_volume_driven(self) -> bool:
        """是否成交量驱动"""
        return self.condition_type == ConditionType.VOLUME

    @property
    def is_open_interest_driven(self) -> bool:
        """是否持仓量驱动"""
        return self.condition_type == ConditionType.OPEN_INTEREST or \
               (self.rollover_type == RolloverType.DYNAMIC and self.condition_type is None)


@dataclass
class DataSourceConfig:
    """数据源配置"""
    source: str                       # 数据源名称
    priority: int                     # 优先级（1为最高）
    table_name: Optional[str] = None  # 数据库表名（如适用）


@dataclass
class FutureAsset:
    """期货品种配置"""
    underlying: str                   # 品种代码，如 IF, RB, TA
    name: str                         # 品种名称
    exchange: Exchange               # 交易所
    currency: str = "CNY"            # 币种
    multiplier: Optional[float] = None  # 合约乘数
    tick_size: Optional[float] = None   # 最小变动单位
    contract_months: List[int] = field(default_factory=list)  # 合约月份列表
    configs: List[RolloverConfig] = field(default_factory=list)  # 展期配置列表

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.exchange, str):
            self.exchange = Exchange(self.exchange)
        if isinstance(self.configs, list) and len(self.configs) > 0:
            if isinstance(self.configs[0], dict):
                self.configs = [RolloverConfig(**cfg) for cfg in self.configs]

    def get_contract_code(self, year: int, month: int) -> str:
        """
        生成合约代码

        郑商所特殊规则：1位年份 + 2位月份
        其他交易所：2位年份 + 2位月份

        Args:
            year: 年份（完整4位）
            month: 月份（1-12）

        Returns:
            合约代码，如 "TA409" 或 "RB2409"
        """
        if self.exchange == Exchange.ZCE:
            # 郑商所：1位年份 + 2位月份
            year_digit = year % 10
            return f"{self.underlying}{year_digit}{month:02d}"
        else:
            # 其他交易所：2位年份 + 2位月份
            year_short = year % 100
            return f"{self.underlying}{year_short}{month:02d}"

    def parse_contract_code(self, code: str) -> tuple:
        """
        解析合约代码

        Args:
            code: 合约代码，如 "TA409" 或 "RB2409"

        Returns:
            (underlying: str, year: int, month: int)

        Raises:
            ValueError: 如果合约代码格式不正确
        """
        if self.exchange == Exchange.ZCE:
            # 郑商所格式：TA409 (品种 + 1位年份 + 2位月份)
            pattern = rf"^({self.underlying})(\d)(\d{{2}})$"
            match = re.match(pattern, code)
            if match:
                year_digit = int(match.group(2))
                month = int(match.group(3))
                # 根据当前年份推断完整年份
                current_year = date.today().year
                current_digit = current_year % 10

                # 计算可能的年份
                year_base = (current_year // 10) * 10
                if year_digit > current_digit:
                    # 上年份（如当前2024年，看到TA309，应该是2023年9月）
                    year = year_base - 10 + year_digit
                else:
                    # 当前或下年份
                    year = year_base + year_digit

                return self.underlying, year, month
        else:
            # 其他交易所格式：RB2409 (品种 + 2位年份 + 2位月份)
            pattern = rf"^({self.underlying})(\d{{2}})(\d{{2}})$"
            match = re.match(pattern, code)
            if match:
                year = 2000 + int(match.group(2))
                month = int(match.group(3))
                return self.underlying, year, month

        raise ValueError(f"Invalid contract code: {code} for exchange {self.exchange.value}")

    def get_config(self, config_id: str) -> Optional[RolloverConfig]:
        """获取指定ID的展期配置"""
        for cfg in self.configs:
            if cfg.config_id == config_id:
                return cfg
        return None

    def get_active_configs(self) -> List[RolloverConfig]:
        """获取所有启用的展期配置"""
        return [cfg for cfg in self.configs if cfg.update_flag == 1]


@dataclass
class IndexAsset:
    """指数配置"""
    symbol: str                       # 指数代码，如 000300.SH
    name: str                         # 指数名称
    exchange: Exchange               # 交易所
    currency: str = "CNY"            # 币种
    index_type: Optional[str] = None  # 指数类型
    sources: List[DataSourceConfig] = field(default_factory=list)  # 数据源列表
    start_date: Optional[date] = None # 数据开始日期
    update_flag: int = 1              # 是否更新

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.exchange, str):
            self.exchange = Exchange(self.exchange)
        if isinstance(self.start_date, str):
            self.start_date = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        if isinstance(self.sources, list) and len(self.sources) > 0:
            if isinstance(self.sources[0], dict):
                self.sources = [DataSourceConfig(**s) for s in self.sources]

    def get_primary_source(self) -> Optional[DataSourceConfig]:
        """获取主数据源（优先级最高）"""
        if not self.sources:
            return None
        return min(self.sources, key=lambda s: s.priority)


@dataclass
class ETFAsset:
    """ETF配置"""
    symbol: str                       # ETF代码，如 510300.SH
    name: str                         # ETF名称
    exchange: Exchange               # 交易所
    currency: str = "CNY"            # 币种
    underlying_index: Optional[str] = None  # 跟踪的指数代码
    sources: List[DataSourceConfig] = field(default_factory=list)  # 数据源列表
    start_date: Optional[date] = None # 上市日期
    update_flag: int = 1              # 是否更新

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.exchange, str):
            self.exchange = Exchange(self.exchange)
        if isinstance(self.start_date, str):
            self.start_date = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        if isinstance(self.sources, list) and len(self.sources) > 0:
            if isinstance(self.sources[0], dict):
                self.sources = [DataSourceConfig(**s) for s in self.sources]


@dataclass
class ConcatComponent:
    """合成资产组件"""
    symbol: str                       # 组件代码
    start_date: Optional[date] = None # 开始日期
    end_date: Optional[date] = None   # 结束日期（可选，表示至今）

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.start_date, str):
            self.start_date = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        if isinstance(self.end_date, str):
            self.end_date = datetime.strptime(self.end_date, "%Y-%m-%d").date()


@dataclass
class ConcatAsset:
    """合成资产配置"""
    symbol: str                       # 合成资产代码
    name: str                         # 合成资产名称
    description: Optional[str] = None # 描述
    type: str = "concat"             # 类型（concat/merged）
    components: List[ConcatComponent] = field(default_factory=list)  # 组件列表
    update_flag: int = 1              # 是否更新

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.components, list) and len(self.components) > 0:
            if isinstance(self.components[0], dict):
                self.components = [ConcatComponent(**c) for c in self.components]

    def get_component_for_date(self, query_date: date) -> Optional[ConcatComponent]:
        """获取指定日期使用的组件"""
        for comp in self.components:
            if comp.start_date and query_date < comp.start_date:
                continue
            if comp.end_date and query_date > comp.end_date:
                continue
            return comp
        return None


# 辅助函数
def parse_config_id(config_id: str) -> Dict[str, Any]:
    """
    解析配置ID

    Args:
        config_id: 配置ID，如 "IF_S7q4_settle" 或 "CU_D73q13_close_vol"

    Returns:
        解析结果字典
    """
    pattern = r"^([A-Z]+)_(S|D)(\d+)q(\d+)_(settle|close)(_vol)?$"
    match = re.match(pattern, config_id)

    if not match:
        raise ValueError(f"Invalid config_id format: {config_id}")

    return {
        "underlying": match.group(1),
        "rollover_type": RolloverType.STATIC if match.group(2) == "S" else RolloverType.DYNAMIC,
        "roll_start_days": int(match.group(3)),
        "roll_end_days": int(match.group(4)),
        "price_type": PriceType(match.group(5)),
        "is_volume_driven": match.group(6) is not None,
    }


def build_config_id(
    underlying: str,
    rollover_type: RolloverType,
    roll_start: int,
    roll_end: int,
    price_type: PriceType,
    condition_type: Optional[ConditionType] = None
) -> str:
    """
    构建配置ID

    Args:
        underlying: 品种代码
        rollover_type: 展期类型
        roll_start: 开始观察天数
        roll_end: 强制展期天数
        price_type: 价格类型
        condition_type: 动态展期条件类型（仅dynamic时需要）

    Returns:
        配置ID字符串
    """
    type_code = "S" if rollover_type == RolloverType.STATIC else "D"
    base = f"{underlying}_{type_code}{roll_start}q{roll_end}_{price_type.value}"

    if rollover_type == RolloverType.DYNAMIC and condition_type == ConditionType.VOLUME:
        base += "_vol"

    return base

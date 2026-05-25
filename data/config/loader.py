"""
Asset Configuration Loader

Loads asset configuration from YAML file and provides query interface.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import date

from data.config.models import (
    Exchange,
    RollConfig,
    FutureAsset,
    IndexAsset,
    ETFAsset,
    ConcatAsset,
    AssetClass,
)


class AssetConfigLoader:
    """资产配置加载器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化加载器

        Args:
            config_path: 配置文件路径，默认使用 config/assets.yaml
        """
        if config_path is None:
            # 从项目根目录开始查找
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "assets.yaml"

        self.config_path = Path(config_path)
        self.futures: Dict[str, FutureAsset] = {}
        self.indices: Dict[str, IndexAsset] = {}
        self.etfs: Dict[str, ETFAsset] = {}
        self.concat_assets: Dict[str, ConcatAsset] = {}
        self._loaded = False

    def load(self) -> "AssetConfigLoader":
        """
        加载配置文件

        Returns:
            self for method chaining
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 加载期货配置
        for item in data.get("futures", []):
            asset = FutureAsset(**item)
            self.futures[asset.underlying] = asset

        # 加载指数配置
        for item in data.get("indices", []):
            asset = IndexAsset(**item)
            self.indices[asset.symbol] = asset

        # 加载ETF配置
        for item in data.get("etfs", []):
            asset = ETFAsset(**item)
            self.etfs[asset.symbol] = asset

        # 加载合成资产配置
        for item in data.get("concat_assets", []):
            asset = ConcatAsset(**item)
            self.concat_assets[asset.symbol] = asset

        self._loaded = True
        return self

    def ensure_loaded(self):
        """确保配置已加载"""
        if not self._loaded:
            self.load()

    # -------------------- Futures --------------------

    def get_future(self, underlying: str) -> Optional[FutureAsset]:
        """
        获取期货品种配置

        Args:
            underlying: 品种代码，如 "IF", "RB"

        Returns:
            FutureAsset or None
        """
        self.ensure_loaded()
        return self.futures.get(underlying)

    def get_all_futures(self) -> List[FutureAsset]:
        """获取所有期货品种"""
        self.ensure_loaded()
        return list(self.futures.values())

    def get_futures_by_exchange(self, exchange: Exchange) -> List[FutureAsset]:
        """
        按交易所获取期货品种

        Args:
            exchange: 交易所枚举

        Returns:
            期货品种列表
        """
        self.ensure_loaded()
        return [f for f in self.futures.values() if f.exchange == exchange]

    def get_roll_config(self, config_id: str) -> Optional[RollConfig]:
        """
        获取展期配置

        Args:
            config_id: 配置ID，如 "IF_S7q4_settle"

        Returns:
            RollConfig or None
        """
        self.ensure_loaded()
        # 从config_id解析underlying
        underlying = config_id.split("_")[0]
        future = self.futures.get(underlying)
        if future:
            return future.get_config(config_id)
        return None

    def get_all_roll_configs(self) -> List[Tuple[str, RollConfig]]:
        """
        获取所有展期配置

        Returns:
            List of (underlying, RollConfig) tuples
        """
        self.ensure_loaded()
        configs = []
        for underlying, future in self.futures.items():
            for cfg in future.configs:
                configs.append((underlying, cfg))
        return configs

    def get_active_roll_configs(self) -> List[Tuple[str, RollConfig]]:
        """
        获取所有启用的展期配置

        Returns:
            List of (underlying, RollConfig) tuples
        """
        self.ensure_loaded()
        return [(u, c) for u, c in self.get_all_roll_configs() if c.update_flag == 1]

    # -------------------- Indices --------------------

    def get_index(self, symbol: str) -> Optional[IndexAsset]:
        """
        获取指数配置

        Args:
            symbol: 指数代码，如 "000300.SH"

        Returns:
            IndexAsset or None
        """
        self.ensure_loaded()
        return self.indices.get(symbol)

    def get_all_indices(self) -> List[IndexAsset]:
        """获取所有指数"""
        self.ensure_loaded()
        return list(self.indices.values())

    def get_indices_by_source(self, source: str) -> List[IndexAsset]:
        """
        按数据源获取指数

        Args:
            source: 数据源名称，如 "wind", "bbg_excel"

        Returns:
            指数配置列表
        """
        self.ensure_loaded()
        result = []
        for idx in self.indices.values():
            for s in idx.sources:
                if s.source == source:
                    result.append(idx)
                    break
        return result

    # -------------------- ETFs --------------------

    def get_etf(self, symbol: str) -> Optional[ETFAsset]:
        """
        获取ETF配置

        Args:
            symbol: ETF代码，如 "510300.SH"

        Returns:
            ETFAsset or None
        """
        self.ensure_loaded()
        return self.etfs.get(symbol)

    def get_all_etfs(self) -> List[ETFAsset]:
        """获取所有ETF"""
        self.ensure_loaded()
        return list(self.etfs.values())

    # -------------------- Concat Assets --------------------

    def get_concat_asset(self, symbol: str) -> Optional[ConcatAsset]:
        """
        获取合成资产配置

        Args:
            symbol: 合成资产代码，如 "CYB_CONCAT"

        Returns:
            ConcatAsset or None
        """
        self.ensure_loaded()
        return self.concat_assets.get(symbol)

    def get_all_concat_assets(self) -> List[ConcatAsset]:
        """获取所有合成资产"""
        self.ensure_loaded()
        return list(self.concat_assets.values())

    # -------------------- Statistics --------------------

    def get_statistics(self) -> dict:
        """
        获取配置统计信息

        Returns:
            统计字典
        """
        self.ensure_loaded()

        total_roll_configs = sum(len(f.configs) for f in self.futures.values())
        active_roll_configs = sum(
            len([c for c in f.configs if c.update_flag == 1])
            for f in self.futures.values()
        )

        # 按交易所统计期货
        futures_by_exchange = {}
        for f in self.futures.values():
            ex = f.exchange.value
            futures_by_exchange[ex] = futures_by_exchange.get(ex, 0) + 1

        # 按数据源统计指数
        indices_by_source = {}
        for idx in self.indices.values():
            source = idx.get_primary_source()
            if source:
                src = source.source
                indices_by_source[src] = indices_by_source.get(src, 0) + 1

        return {
            "futures_count": len(self.futures),
            "indices_count": len(self.indices),
            "etfs_count": len(self.etfs),
            "concat_assets_count": len(self.concat_assets),
            "total_roll_configs": total_roll_configs,
            "active_roll_configs": active_roll_configs,
            "futures_by_exchange": futures_by_exchange,
            "indices_by_source": indices_by_source,
        }

    def print_statistics(self):
        """打印配置统计信息"""
        stats = self.get_statistics()

        print("=" * 60)
        print("Asset Configuration Statistics")
        print("=" * 60)
        print(f"Futures: {stats['futures_count']}")
        print(f"  - Total roll configs: {stats['total_roll_configs']}")
        print(f"  - Active roll configs: {stats['active_roll_configs']}")
        print(f"\nFutures by Exchange:")
        for ex, count in sorted(stats['futures_by_exchange'].items()):
            print(f"  - {ex}: {count}")
        print(f"\nIndices: {stats['indices_count']}")
        print(f"  - By source:")
        for src, count in sorted(stats['indices_by_source'].items()):
            print(f"    - {src}: {count}")
        print(f"\nETFs: {stats['etfs_count']}")
        print(f"Concat Assets: {stats['concat_assets_count']}")
        print("=" * 60)


# 全局单例
_loader: Optional[AssetConfigLoader] = None


def get_loader() -> AssetConfigLoader:
    """
    获取全局配置加载器

    Returns:
        AssetConfigLoader 单例
    """
    global _loader
    if _loader is None:
        _loader = AssetConfigLoader().load()
    return _loader

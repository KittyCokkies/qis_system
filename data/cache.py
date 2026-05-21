import hashlib
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger


class DataCache:
    """数据缓存管理器

    支持内存缓存和本地文件缓存，用于减少重复的数据获取请求
    """

    def __init__(self, cache_dir: str = "./data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict = {}
        logger.info(f"DataCache initialized with directory: {cache_dir}")

    def _get_cache_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        param_str = "_".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
        hash_key = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"{prefix}_{hash_key}"

    def _get_cache_file(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.pkl"

    def get(
        self,
        cache_key: str,
        max_age_hours: int = 24
    ) -> Optional[Any]:
        """获取缓存数据

        Args:
            cache_key: 缓存键
            max_age_hours: 缓存最大有效期（小时）

        Returns:
            缓存数据，不存在或过期返回None
        """
        # 先查内存
        if cache_key in self._memory_cache:
            data, timestamp = self._memory_cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=max_age_hours):
                logger.debug(f"Memory cache hit: {cache_key}")
                return data
            else:
                del self._memory_cache[cache_key]

        # 再查文件
        cache_file = self._get_cache_file(cache_key)
        if cache_file.exists():
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - mtime < timedelta(hours=max_age_hours):
                try:
                    with open(cache_file, "rb") as f:
                        data = pickle.load(f)
                    # 同步到内存
                    self._memory_cache[cache_key] = (data, mtime)
                    logger.debug(f"File cache hit: {cache_key}")
                    return data
                except Exception as e:
                    logger.warning(f"Failed to load cache file: {e}")
            else:
                # 过期删除
                cache_file.unlink()

        return None

    def set(self, cache_key: str, data: Any) -> bool:
        """设置缓存数据

        Args:
            cache_key: 缓存键
            data: 缓存数据

        Returns:
            是否成功
        """
        try:
            # 内存缓存
            self._memory_cache[cache_key] = (data, datetime.now())

            # 文件缓存
            cache_file = self._get_cache_file(cache_key)
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)

            logger.debug(f"Cache set: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"Failed to set cache: {e}")
            return False

    def invalidate(self, prefix: Optional[str] = None):
        """清除缓存

        Args:
            prefix: 如果指定，只清除匹配的缓存
        """
        # 清除内存缓存
        if prefix:
            keys_to_remove = [k for k in self._memory_cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._memory_cache[k]
        else:
            self._memory_cache.clear()

        # 清除文件缓存
        for cache_file in self.cache_dir.glob("*.pkl"):
            if prefix is None or cache_file.stem.startswith(prefix):
                cache_file.unlink()

        logger.info(f"Cache invalidated: prefix={prefix}")

    def cache_dataframe(
        self,
        df: pd.DataFrame,
        prefix: str,
        **kwargs
    ) -> bool:
        """专门用于缓存DataFrame"""
        cache_key = self._get_cache_key(prefix, **kwargs)
        return self.set(cache_key, df)

    def get_dataframe(
        self,
        prefix: str,
        max_age_hours: int = 24,
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """获取缓存的DataFrame"""
        cache_key = self._get_cache_key(prefix, **kwargs)
        return self.get(cache_key, max_age_hours)

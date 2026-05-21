import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """数据库配置"""
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "qis_db"
    user: str = "postgres"
    password: str = ""

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisConfig(BaseSettings):
    """Redis缓存配置"""
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class DataSourceConfig(BaseSettings):
    """数据源配置"""
    model_config = SettingsConfigDict(env_prefix="DATA_")

    tushare_token: Optional[str] = Field(default=None, alias="TUSHARE_TOKEN")
    akshare_cache_dir: str = "./data/cache"


class Settings(BaseSettings):
    """全局配置类"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 项目根目录
    project_root: Path = Path(__file__).parent.parent

    # 调试模式
    debug: bool = False

    # 时区
    timezone: str = "Asia/Shanghai"

    # 子配置
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    datasource: DataSourceConfig = DataSourceConfig()

    # 回测配置
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.001

    class Config:
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    """获取全局配置（单例模式）"""
    return Settings()

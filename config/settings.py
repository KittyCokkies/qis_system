import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """PostgreSQL数据库配置（本地存储）"""
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "qis_db"
    user: str = "postgres"
    password: str = ""

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class TonglianConfig(BaseSettings):
    """通联数据库配置 (MySQL)"""
    model_config = SettingsConfigDict(env_prefix="TONGLIAN_")

    host: str = "192.168.27.112"
    port: int = 3306
    user: str = "swhyjc"
    password: str = "yesData@123yyds"
    database: str = "datayesdb"
    charset: str = "utf8mb4"

    @property
    def url(self) -> str:
        from urllib.parse import quote
        # 对密码进行 URL 编码（处理@等特殊字符）
        encoded_password = quote(self.password, safe='')
        return f"mysql+pymysql://{self.user}:{encoded_password}@{self.host}:{self.port}/{self.database}?charset={self.charset}"


class SwifquantConfig(BaseSettings):
    """Swifquant数据库配置 (MySQL)"""
    model_config = SettingsConfigDict(env_prefix="SWIFQUANT_")

    host: str = "192.168.173.123"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "swifquant"
    charset: str = "utf8mb4"

    @property
    def url(self) -> str:
        from urllib.parse import quote
        encoded_password = quote(self.password, safe='')
        return f"mysql+pymysql://{self.user}:{encoded_password}@{self.host}:{self.port}/{self.database}?charset={self.charset}"


class WindConfig(BaseSettings):
    """万得Wind配置"""
    model_config = SettingsConfigDict(env_prefix="WIND_")

    # WindPy通常使用本地终端授权，不需要额外配置
    # 这里预留配置项用于未来扩展
    username: Optional[str] = None
    password: Optional[str] = None
    license_path: Optional[str] = None  # 授权文件路径


class FTPConfig(BaseSettings):
    """FTP文件服务器配置"""
    model_config = SettingsConfigDict(env_prefix="FTP_")

    host: str = ""
    port: int = 21
    user: str = ""
    password: str = ""
    base_path: str = "/"  # 基础路径
    passive_mode: bool = True  # 被动模式
    encoding: str = "utf-8"


class DolphinDBConfig(BaseSettings):
    """DolphinDB时序数据库配置"""
    model_config = SettingsConfigDict(env_prefix="DOLPHINDB_")

    host: str = "localhost"
    port: int = 8848
    user: str = "admin"
    password: str = "123456"
    # 集群配置（预留）
    cluster_mode: bool = False
    cluster_nodes: list = []


class RedisConfig(BaseSettings):
    """Redis缓存配置"""
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class DataSourceConfig(BaseSettings):
    """第三方数据源配置"""
    model_config = SettingsConfigDict(env_prefix="DATA_")

    # Tushare
    tushare_token: Optional[str] = Field(default=None, alias="TUSHARE_TOKEN")

    # AKShare
    akshare_cache_dir: str = "./data/cache"

    # 数据源优先级（用于多源数据冲突时选择）
    priority: list = Field(default_factory=lambda: ["wind", "tonglian", "tushare", "akshare", "ftp"])


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

    # 数据库配置
    database: DatabaseConfig = DatabaseConfig()          # 本地PostgreSQL
    tonglian: TonglianConfig = TonglianConfig()          # 通联MySQL
    swifquant: SwifquantConfig = SwifquantConfig()       # Swifquant MySQL
    wind: WindConfig = WindConfig()                      # 万得
    ftp: FTPConfig = FTPConfig()                         # FTP
    dolphindb: DolphinDBConfig = DolphinDBConfig()       # DolphinDB
    redis: RedisConfig = RedisConfig()                   # Redis缓存

    # 第三方数据源配置
    datasource: DataSourceConfig = DataSourceConfig()

    # 回测配置
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.001

    # 数据存储配置
    data_storage: Dict[str, Any] = Field(default_factory=lambda: {
        "raw_data_path": "./data/raw",
        "processed_data_path": "./data/processed",
        "cache_path": "./data/cache",
        "backup_path": "./data/backup",
    })


@lru_cache()
def get_settings() -> Settings:
    """获取全局配置（单例模式）"""
    return Settings()

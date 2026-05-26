import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import get_settings

# Alembic 配置对象，提供对正在使用的 .ini 文件中值的访问
config = context.config

# 解释 Python 日志的配置文件
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从项目设置获取数据库 URL
settings = get_settings()
DATABASE_URL = settings.database.url

# 用于自动生成支持（可选，如果使用 SQLAlchemy 模型）
target_metadata = None

# 可以从配置中获取其他值，由 env.py 的需求定义：
# my_important_option = config.get_main_option("my_important_option")
# ... 等等


def run_migrations_offline() -> None:
    """在离线模式下运行迁移"""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在在线模式下运行迁移"""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

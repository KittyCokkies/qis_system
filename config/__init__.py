from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
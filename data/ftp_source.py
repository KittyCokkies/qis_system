"""
FTP文件数据源

从FTP服务器读取数据文件（CSV、Excel、Parquet等）
"""
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union, Callable

import pandas as pd
from ftplib import FTP, FTP_TLS
from loguru import logger

from config import get_settings
from data.base import DataSourceBase


class FTPSource(DataSourceBase):
    """FTP文件数据源

    从FTP服务器读取数据文件，支持多种格式

    Attributes:
        host: FTP服务器地址
        port: 端口
        user: 用户名
        password: 密码
        ftp: FTP连接对象
    """

    SUPPORTED_FORMATS = ['.csv', '.xlsx', '.xls', '.parquet', '.json', '.txt']

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False
    ):
        super().__init__()
        settings = get_settings()

        self.host = host or settings.ftp.host
        self.port = port or settings.ftp.port
        self.user = user or settings.ftp.user
        self.password = password or settings.ftp.password
        self.base_path = settings.ftp.base_path
        self.use_tls = use_tls
        self.encoding = settings.ftp.encoding

        self.ftp: Optional[FTP] = None
        self._connect()

    def _connect(self):
        """建立FTP连接"""
        if not self.host or not self.user:
            logger.warning("FTP credentials not configured")
            return

        try:
            if self.use_tls:
                self.ftp = FTP_TLS()
                self.ftp.connect(self.host, self.port)
                self.ftp.login(self.user, self.password)
                self.ftp.prot_p()  # 切换到安全模式
            else:
                self.ftp = FTP()
                self.ftp.connect(self.host, self.port)
                self.ftp.login(self.user, self.password)

            self.ftp.set_pasv(True)  # 被动模式
            self.ftp.encoding = self.encoding

            logger.info(f"FTP connected: {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"FTP connection failed: {e}")
            self.ftp = None

    def ensure_connected(self) -> bool:
        """确保连接状态"""
        if self.ftp is None:
            self._connect()
        return self.ftp is not None

    def list_files(self, path: Optional[str] = None, pattern: Optional[str] = None) -> List[str]:
        """列出FTP目录中的文件

        Args:
            path: 目录路径
            pattern: 文件名匹配模式（如 '*.csv'）

        Returns:
            文件列表
        """
        if not self.ensure_connected():
            return []

        try:
            target_path = path or self.base_path
            self.ftp.cwd(target_path)

            files = []
            self.ftp.retrlines('NLST', files.append)

            # 过滤文件
            if pattern:
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f, pattern)]

            return files

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []

    def download_file(self, remote_path: str, local_path: Optional[str] = None) -> Optional[str]:
        """下载文件

        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径，None则使用临时文件

        Returns:
            本地文件路径
        """
        if not self.ensure_connected():
            return None

        try:
            if local_path is None:
                fd, local_path = tempfile.mkstemp()
                os.close(fd)

            with open(local_path, 'wb') as f:
                self.ftp.retrbinary(f'RETR {remote_path}', f.write)

            logger.debug(f"Downloaded: {remote_path} -> {local_path}")
            return local_path

        except Exception as e:
            logger.error(f"Failed to download {remote_path}: {e}")
            return None

    def read_file(
        self,
        remote_path: str,
        file_format: Optional[str] = None,
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """读取远程文件为DataFrame

        Args:
            remote_path: 远程文件路径
            file_format: 文件格式，None则自动识别
            **kwargs: 读取参数

        Returns:
            DataFrame或None
        """
        if not self.ensure_connected():
            return None

        # 自动识别格式
        if file_format is None:
            ext = Path(remote_path).suffix.lower()
            file_format = ext if ext in self.SUPPORTED_FORMATS else '.csv'

        try:
            # 读取到内存
            buffer = io.BytesIO()
            self.ftp.retrbinary(f'RETR {remote_path}', buffer.write)
            buffer.seek(0)

            # 根据格式解析
            if file_format == '.csv':
                df = pd.read_csv(buffer, **kwargs)
            elif file_format in ['.xlsx', '.xls']:
                df = pd.read_excel(buffer, **kwargs)
            elif file_format == '.parquet':
                df = pd.read_parquet(buffer, **kwargs)
            elif file_format == '.json':
                df = pd.read_json(buffer, **kwargs)
            else:
                logger.error(f"Unsupported format: {file_format}")
                return None

            logger.info(f"Read file: {remote_path}, shape: {df.shape}")
            return df

        except Exception as e:
            logger.error(f"Failed to read {remote_path}: {e}")
            return None

    def upload_file(self, local_path: str, remote_path: Optional[str] = None) -> bool:
        """上传文件

        Args:
            local_path: 本地文件路径
            remote_path: 远程路径，None则使用文件名

        Returns:
            是否成功
        """
        if not self.ensure_connected():
            return False

        try:
            if remote_path is None:
                remote_path = Path(local_path).name

            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {remote_path}', f)

            logger.info(f"Uploaded: {local_path} -> {remote_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False

    def sync_directory(
        self,
        remote_dir: str,
        local_dir: str,
        pattern: Optional[str] = None,
        overwrite: bool = False
    ) -> List[str]:
        """同步远程目录到本地

        Args:
            remote_dir: 远程目录
            local_dir: 本地目录
            pattern: 文件匹配模式
            overwrite: 是否覆盖现有文件

        Returns:
            下载的文件列表
        """
        if not self.ensure_connected():
            return []

        Path(local_dir).mkdir(parents=True, exist_ok=True)

        files = self.list_files(remote_dir, pattern)
        downloaded = []

        for filename in files:
            local_path = Path(local_dir) / filename

            if local_path.exists() and not overwrite:
                logger.debug(f"Skipping existing file: {filename}")
                continue

            remote_path = f"{remote_dir}/{filename}"
            result = self.download_file(remote_path, str(local_path))

            if result:
                downloaded.append(filename)

        logger.info(f"Synced {len(downloaded)} files from {remote_dir}")
        return downloaded

    def read_timeseries_data(
        self,
        remote_path: str,
        date_column: str = 'date',
        symbol_column: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """读取时间序列数据

        专门用于读取股票/期货/期权等金融时间序列数据

        Args:
            remote_path: 远程文件路径
            date_column: 日期列名
            symbol_column: 代码列名
            **kwargs: 其他读取参数

        Returns:
            DataFrame
        """
        df = self.read_file(remote_path, **kwargs)

        if df is None or df.empty:
            return pd.DataFrame()

        # 标准化日期列
        if date_column in df.columns:
            df[date_column] = pd.to_datetime(df[date_column])
            df.set_index(date_column, inplace=True)

        # 标准化代码列
        if symbol_column and symbol_column in df.columns:
            df[symbol_column] = df[symbol_column].apply(self.normalize_symbol)

        return df

    def get_daily_price(
        self,
        symbol: Union[str, List[str]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日频数据（从FTP文件）

        假设文件按日期或代码组织
        """
        if isinstance(symbol, str):
            symbol = [symbol]

        all_data = []

        for sym in symbol:
            # 构建文件路径，假设格式: /data/daily/{symbol}.csv
            remote_path = f"{self.base_path}/daily/{sym.replace('.', '_')}.csv"

            df = self.read_file(remote_path)

            if df is not None and not df.empty:
                df['symbol'] = sym
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)

        # 日期过滤
        if start_date:
            result = result[result.index >= start_date]
        if end_date:
            result = result[result.index <= end_date]

        # 字段选择
        if fields:
            available_cols = ['symbol'] + [c for c in fields if c in result.columns]
            result = result[available_cols]

        return result

    def get_fundamentals(
        self,
        symbol: Union[str, List[str]],
        fields: Optional[List[str]] = None,
        date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """获取基本面数据"""
        # 假设财务数据存储在特定文件中
        remote_path = f"{self.base_path}/fundamentals/financial_data.csv"
        df = self.read_file(remote_path)

        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(symbol, list):
            df = df[df['symbol'].isin(symbol)]
        else:
            df = df[df['symbol'] == symbol]

        if date and 'report_date' in df.columns:
            df = df[df['report_date'] <= date]

        return df

    def get_index_components(self, index_code: str, date: Optional[datetime] = None) -> List[str]:
        """获取指数成分股"""
        remote_path = f"{self.base_path}/index_components/{index_code.replace('.', '_')}.csv"
        df = self.read_file(remote_path)

        if df is not None and 'symbol' in df.columns:
            return df['symbol'].tolist()
        return []

    def get_trade_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历"""
        remote_path = f"{self.base_path}/calendar/trade_calendar_{market}.csv"
        df = self.read_file(remote_path)

        if df is not None:
            df['date'] = pd.to_datetime(df['date'])

            if start_date:
                df = df[df['date'] >= start_date]
            if end_date:
                df = df[df['date'] <= end_date]

        return df if df is not None else pd.DataFrame()

    def get_minute_price(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = "1min"
    ) -> pd.DataFrame:
        """获取分钟数据"""
        remote_path = f"{self.base_path}/minute/{symbol.replace('.', '_')}_{freq}.parquet"
        return self.read_file(remote_path) or pd.DataFrame()

    def __del__(self):
        """析构时关闭连接"""
        if self.ftp:
            try:
                self.ftp.quit()
                logger.info("FTP connection closed")
            except:
                pass

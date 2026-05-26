"""
Bloomberg Excel 数据同步

从 Excel 文件读取 Bloomberg 数据

期望格式:
    文件: bbg_data_YYYYMMDD.xlsx
    工作表: 每个工作表以 Bloomberg 代码命名 (如 'SPX Index', 'USGG10YR Index')
    列: date (YYYY-MM-DD), nav (数值)
"""

from datetime import date
from pathlib import Path
from typing import List, Optional
import pandas as pd
from loguru import logger

from data.config.loader import AssetConfigLoader, IndexAsset
from data.database import DatabaseManager


class BBGExcelSync:
    """Bloomberg Excel 数据同步器"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config_loader = AssetConfigLoader()
        self._file_path: Optional[Path] = None
        self._data: dict = {}  # 工作表名称 -> DataFrame

    def load_file(self, file_path: Path) -> bool:
        """
        加载 Excel 文件

        Args:
            file_path: Excel 文件路径

        Returns:
            成功返回 True
        """
        try:
            self._file_path = Path(file_path)

            # 读取所有工作表
            xl = pd.ExcelFile(self._file_path)

            for sheet_name in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet_name)

                # 验证列
                if 'date' not in df.columns or 'nav' not in df.columns:
                    logger.warning(f"工作表 {sheet_name}: 缺少必需的列 (date, nav)")
                    continue

                # 转换日期列
                df['date'] = pd.to_datetime(df['date']).dt.date

                self._data[sheet_name] = df
                logger.debug(f"Loaded {len(df)} records from sheet {sheet_name}")

            logger.info(f"已从 {file_path} 加载 {len(self._data)} 个工作表")
            return True

        except Exception as e:
            logger.error(f"加载 Excel 文件失败: {e}")
            return False

    def get_active_indices(self) -> List[IndexAsset]:
        """从配置中获取 BBG 指数"""
        return self.config_loader.get_indices_by_source("bbg_excel")

    def sync_index_daily(self, symbol: str, sync_date: date, full_refresh: bool = False) -> int:
        """
        同步指数日频数据

        代码应与 Excel 文件中的工作表名称匹配
        常用 BBG 代码: 'SPX Index', 'NDX Index', 'SX5E Index' 等
        """
        if not self._data:
            raise RuntimeError("No Excel file loaded")

        # 查找匹配的工作表（处理命名变化）
        sheet_name = None
        for name in self._data.keys():
            if symbol in name or name in symbol:
                sheet_name = name
                break

        if sheet_name is None:
            logger.warning(f"未找到代码 {symbol} 的工作表")
            return 0

        df = self._data[sheet_name]

        # 筛选同步日期
        day_data = df[df['date'] == sync_date]

        if day_data.empty:
            logger.debug(f"{symbol} 在 {sync_date} 无数据")
            return 0

        record = day_data.iloc[0]

        if full_refresh:
            # 先删除现有数据
            self.db.execute(
                "DELETE FROM prices_index WHERE symbol = %s AND date = %s",
                (symbol, sync_date)
            )

        self.db.execute("""
            INSERT INTO prices_index
            (symbol, date, close, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                close = EXCLUDED.close,
                source = EXCLUDED.source
        """, (
            symbol, sync_date, record['nav'], 'bbg_excel'
        ))

        logger.debug(f"Imported {symbol} for {sync_date}: {record['nav']}")
        return 1

    def sync_index_history(self, symbol: str, start_date: date, end_date: date) -> int:
        """同步指数历史数据"""
        if not self._data:
            raise RuntimeError("No Excel file loaded")

        sheet_name = None
        for name in self._data.keys():
            if symbol in name or name in symbol:
                sheet_name = name
                break

        if sheet_name is None:
            logger.warning(f"No sheet found for symbol {symbol}")
            return 0

        df = self._data[sheet_name]

        # 筛选日期范围
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        range_data = df[mask]

        if range_data.empty:
            logger.warning(f"{symbol} 从 {start_date} 到 {end_date} 无数据")
            return 0

        records = range_data.to_dict('records')
        for record in records:
            self.db.execute("""
                INSERT INTO prices_index
                (symbol, date, close, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    close = EXCLUDED.close,
                    source = EXCLUDED.source
            """, (
                symbol, record['date'], record['nav'], 'bbg_excel'
            ))

        return len(records)

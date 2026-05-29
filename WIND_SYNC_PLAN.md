# 万得数据同步方案

## 1. 数据来源概述

根据配置文件 `config_wind_etl.xlsx`，需要同步 **78个万得数据代码**，分为以下类别：

| 数据类别 | 数量 | 说明 |
|---------|------|------|
| underlying_index | 37 | 底层指数（股指、债券指数、商品指数） |
| underlying_etf | 17 | ETF基金 |
| dividend_yield | 10 | 股息率数据 |
| 10yrates | 6 | 10年期利率 |
| fx | 4 | 外汇汇率 |
| r007 | 1 | 银行间回购利率 |
| underlying_otc | 3 | 场外基金 |

## 2. 目标数据库表设计

### 表1: qis_fx_quote_info（外汇汇率）

```sql
CREATE TABLE qis_fx_quote_info (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    asset_id VARCHAR(50) NOT NULL,
    ticker VARCHAR(50) NOT NULL,  -- 万得代码如 M0000185
    value DECIMAL(18, 8),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, asset_id)
);

CREATE INDEX idx_fx_quote_date ON qis_fx_quote_info(trade_date);
CREATE INDEX idx_fx_quote_ticker ON qis_fx_quote_info(ticker);
```

**包含数据：**
- M0000185, M0000186, M0000187, M0000188（人民币外汇汇率相关）

### 表2: qis_market_data（市场数据）

```sql
CREATE TABLE qis_market_data (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    asset_id VARCHAR(50) NOT NULL,
    ticker VARCHAR(50) NOT NULL,
    fields VARCHAR(50) NOT NULL,  -- r007, rates, dividendyield2
    value DECIMAL(18, 8),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, asset_id, fields)
);

CREATE INDEX idx_market_date ON qis_market_data(trade_date);
CREATE INDEX idx_market_ticker ON qis_market_data(ticker);
CREATE INDEX idx_market_fields ON qis_market_data(fields);
```

**包含数据：**
- **r007**: M0041653（银行间7天回购利率）
- **10yrates**: B2559386, G0000891, G1235664, G8322945, M0325687, S0059749
- **dividend_yield**: 000300.SH, 000688.SH, 000905.SH, 000906.SH, DJI.GI, GDAXI.GI, HSCEI.HI, N225.GI, NDX.GI, SPX.GI

### 表3: qis_underlying_quote_info（底层标的价格）

```sql
CREATE TABLE qis_underlying_quote_info (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    asset_id VARCHAR(100) NOT NULL,
    ticker VARCHAR(50) NOT NULL,
    asset_type VARCHAR(50),  -- underlying_etf, underlying_index, underlying_otc
    fields VARCHAR(50) NOT NULL,  -- close, NAV_adj
    value DECIMAL(18, 8),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, asset_id, fields)
);

CREATE INDEX idx_underlying_date ON qis_underlying_quote_info(trade_date);
CREATE INDEX idx_underlying_ticker ON qis_underlying_quote_info(ticker);
CREATE INDEX idx_underlying_type ON qis_underlying_quote_info(asset_type);
```

**包含数据：**
- **ETF (17个)**: 588000.SH(科创50ETF), 159915.SZ(创业板ETF), 562500.SH(机器人ETF), 等
- **指数 (37个)**: 000300.SH(沪深300), 000688.SH(科创50), HSI.HI(恒生指数), 等
- **场外基金 (3个)**: 007994.OF, 110026.OF, 501018.SH

## 3. 同步脚本设计

### 脚本结构

```
scripts/
├── sync_wind_data.py      # 主同步脚本
├── wind_api_client.py      # 万得API客户端封装
└── config_wind_etl.xlsx    # 配置文件（从F:\airflow_qis\local\复制）
```

### 主脚本核心逻辑

```python
#!/usr/bin/env python3
"""
万得数据同步脚本
每天下午16:30运行，同步前一日数据
"""
import pandas as pd
from datetime import datetime, date, timedelta
from loguru import logger
import sys

from wind_api_client import WindAPI
from data.database import DatabaseManager

CONFIG_FILE = 'scripts/config_wind_etl.xlsx'

class WindDataSync:
    def __init__(self):
        self.db = DatabaseManager()
        self.wind = WindAPI()
        self.config = pd.read_excel(CONFIG_FILE)

    def get_last_sync_date(self, table, ticker, fields=None):
        """获取某代码的最后同步日期"""
        # 实现查询逻辑
        pass

    def sync_fx_data(self):
        """同步外汇数据到 qis_fx_quote_info"""
        fx_config = self.config[self.config['table_name'] == 'qis_fx_quote_info']
        # 使用Wind EDB接口获取数据
        pass

    def sync_market_data(self):
        """同步市场数据到 qis_market_data"""
        market_config = self.config[self.config['table_name'] == 'qis_market_data']
        # 区分EDB和WSD接口
        pass

    def sync_underlying_data(self):
        """同步底层标的数据到 qis_underlying_quote_info"""
        underlying_config = self.config[self.config['table_name'] == 'qis_underlying_quote_info']
        # 使用WSD接口获取收盘价/净值
        pass

    def run(self):
        """执行同步"""
        logger.info("万得数据同步开始")
        self.sync_fx_data()
        self.sync_market_data()
        self.sync_underlying_data()
        logger.info("万得数据同步完成")

if __name__ == "__main__":
    sync = WindDataSync()
    sync.run()
```

### 万得API接口说明

| 数据类别 | Wind函数 | 参数示例 |
|---------|---------|---------|
| fx (EDB) | `w.edb(ticker, start_date, end_date)` | M0000185 |
| r007/10yrates (EDB) | `w.edb(ticker, start_date, end_date, Fill='Previous')` | M0041653 |
| dividend_yield (WSD) | `w.wsd(ticker, fields, start_date, end_date)` | 000300.SH, dividendyield2 |
| underlying (WSD) | `w.wsd(ticker, fields, start_date, end_date)` | 588000.SH, close/NAV_adj |

## 4. 定时任务设置

### Windows任务计划程序

创建 `setup_wind_sync_task.bat`:

```batch
@echo off
chcp 65001

:: 删除旧任务
schtasks /delete /tn "QIS\Sync Wind Data" /f 2>nul

:: 创建新任务 - 每天16:30运行
schtasks /create ^
  /tn "QIS\Sync Wind Data" ^
  /tr "F:\qis_system\venv\Scripts\python.exe F:\qis_system\scripts\sync_wind_data.py" ^
  /sc daily ^
  /st 16:30 ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /description "万得数据每日同步任务，下午16:30运行"

echo Wind数据同步任务已创建
echo 运行时间: 每天 16:30
pause
```

### 验证命令

```cmd
:: 查看任务
schtasks /query /tn "QIS\Sync Wind Data" /fo list

:: 手动运行测试
schtasks /run /tn "QIS\Sync Wind Data"
```

## 5. 实施步骤

1. **创建数据库表**
   - 执行上述3个CREATE TABLE语句

2. **复制配置文件**
   - 复制 `F:\airflow_qis\local\config_wind_etl.xlsx` 到 `F:\qis_system\scripts\`

3. **开发同步脚本**
   - 创建 `wind_api_client.py`（万得API封装）
   - 创建 `sync_wind_data.py`（主同步脚本）

4. **测试运行**
   - 手动运行脚本验证数据同步正确

5. **设置定时任务**
   - 运行 `setup_wind_sync_task.bat`
   - 验证任务已创建

## 6. 注意事项

1. **万得API权限**: 确保本机已安装Wind金融终端且API可用
2. **数据起始日期**: 配置文件中有start_date字段，首次同步从此日期开始
3. **增量同步**: 建议实现增量同步，只同步新增数据
4. **错误处理**: 需处理万得API连接失败、数据缺失等异常情况
5. **日志记录**: 使用loguru记录同步日志，便于排查问题

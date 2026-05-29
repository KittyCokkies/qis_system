# 彭博Excel数据同步脚本 (sync_bloomberg_excel.py)

## 功能概述

自动读取彭博Excel文件 (`bbg_data_new.xlsx`)，将数据分类同步到本地PostgreSQL数据库。

### 数据来源

**文件路径：** `Z:\每日更新\数据\彭博\bbg_data_new.xlsx`

**工作表命名规则：**
- 股票指数：`{代码} Index` (如 `STAR50 Index`)
- 外汇汇率：`{代码} Curncy` (如 `CNH L160 Curncy`)
- DMA期货价格：`DMA_settle`, `DMA_last`
- DMA期货成交量：`HCTA_volume`
- DMA通知日：`DMA_ltd` (first_notice_date)

### 数据映射规则

| 数据来源 | 工作表示例 | 目标表 | 说明 |
|---------|-----------|--------|------|
| 股票指数 | STAR50 Index, VIX Index | prices_index | 指数行情数据 |
| 外汇汇率 | CNH L160 Curncy, EURCNH L160 Curncy | fx_rates | 外汇即期汇率 |
| DMA结算价 | DMA_settle, HCTA_settle | prices_future | 期货结算价格 |
| DMA最新价 | DMA_last | prices_future | 期货最新价格 |
| DMA成交量 | HCTA_volume | prices_future | 期货成交量 |
| DMA通知日 | DMA_ltd, HCTA_ltd | assets.delist_date | 第一通知日期 |

## 运行方式

```bash
# 执行同步
python scripts/sync_bloomberg_excel.py
```

### 运行时机

建议每日 **08:30** 运行（在开盘前获取前日收盘数据）。

---

## 涉及的数据库表

### 1. assets - 资产主表

存储所有可交易标的的基础信息，包括彭博代码映射。

**表结构：**

| 字段名 | 类型 | 说明 | 约束 |
|--------|------|------|------|
| symbol | VARCHAR(50) | 标的代码 | PRIMARY KEY |
| underlying | VARCHAR(10) | 底层品种代码 | NOT NULL |
| name | VARCHAR(100) | 标的名称 | - |
| asset_class | VARCHAR(20) | 资产类别 | CHECK (stock/future/index/etf/bond/option/commodity/fund/fx/macro) |
| exchange | VARCHAR(10) | 交易所 | - |
| currency | VARCHAR(3) | 币种 | DEFAULT 'CNY' |
| contract_month | VARCHAR(6) | 合约月份(期货) | - |
| list_date | DATE | 上市日期 | - |
| delist_date | DATE | 退市/到期/第一通知日 | - |
| multiplier | DECIMAL(10,4) | 合约乘数 | - |
| tick_size | DECIMAL(10,4) | 最小变动单位 | - |
| is_active | BOOLEAN | 是否可交易 | DEFAULT TRUE |
| update_time | TIMESTAMP | 更新时间 | DEFAULT CURRENT_TIMESTAMP |

**示例数据：**

```json
// 外汇资产 (来自彭博)
{
  "symbol": "CNH L160 Curncy",
  "underlying": "CNH",
  "name": "CNH L160 Curncy",
  "asset_class": "fx",
  "exchange": "BLOOMBERG",
  "currency": "CNY",
  "is_active": true,
  "update_time": "2026-05-29 15:27:18"
}

// DMA期货合约
{
  "symbol": "DMU02 Index",
  "underlying": "DMA",
  "name": "DMU02 Index",
  "asset_class": "future",
  "exchange": "CME",
  "delist_date": "2002-09-19",
  "is_active": true,
  "update_time": "2026-05-29 15:21:21"
}

// 股票指数
{
  "symbol": "STAR50 Index",
  "underlying": "STAR50",
  "name": "STAR50 Index",
  "asset_class": "index",
  "exchange": "BLOOMBERG",
  "is_active": true,
  "update_time": "2026-05-29 10:32:21"
}
```

---

### 2. fx_rates - 汇率表

存储外汇汇率数据，来自彭博Excel中的 `*Curncy` 工作表。

**表结构：**

| 字段名 | 类型 | 说明 | 约束 |
|--------|------|------|------|
| symbol | VARCHAR(50) | 彭博代码 | PRIMARY KEY (复合) |
| date | DATE | 日期 | PRIMARY KEY (复合) |
| spot_rate | DECIMAL(12,6) | 即期汇率 | - |
| update_time | TIMESTAMP | 更新时间 | DEFAULT CURRENT_TIMESTAMP |

**外键约束：**
- `symbol` → `assets(symbol)` ON DELETE CASCADE

**示例数据：**

```json
// 离岸人民币汇率
{
  "symbol": "CNH L160 Curncy",
  "date": "2019-01-02",
  "spot_rate": "6.878300",
  "update_time": "2026-05-29 15:27:18"
}

// 欧元兑离岸人民币
{
  "symbol": "EURCNH L160 Curncy",
  "date": "2019-01-02",
  "spot_rate": "7.808700",
  "update_time": "2026-05-29 15:27:22"
}
```

**同步的外汇代码：**

| 彭博代码 | 说明 |
|----------|------|
| CNH L160 Curncy | 美元兑离岸人民币 |
| JPYCNH L160 Curncy | 日元兑离岸人民币 |
| EURCNH L160 Curncy | 欧元兑离岸人民币 |
| HKDCNH L160 Curncy | 港币兑离岸人民币 |
| HKDUSD L160 Curncy | 港币兑美元 |
| HKDCNH Curncy | 港币兑离岸人民币(即期) |
| CNYUSD BFIX Curncy | 美元兑人民币(BFIX) |
| USDCNY Curncy | 美元兑在岸人民币 |
| USDCNH Curncy | 美元兑离岸人民币(即期) |

---

### 3. prices_index - 指数价格表

存储股票指数行情数据，来自彭博Excel中的 `*Index` 工作表。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| symbol | VARCHAR(20) | 指数代码 |
| date | DATE | 交易日期 |
| open | DECIMAL(12,4) | 开盘价 |
| high | DECIMAL(12,4) | 最高价 |
| low | DECIMAL(12,4) | 最低价 |
| close | DECIMAL(12,4) | 收盘价 |
| volume | BIGINT | 成交量 |
| amount | DECIMAL(20,4) | 成交金额 |
| pe_ttm | DECIMAL(10,4) | 市盈率TTM |
| pb_lf | DECIMAL(10,4) | 市净率LF |
| dividend_yield | DECIMAL(8,4) | 股息率 |
| update_time | TIMESTAMP | 更新时间 |

**示例数据：**

```json
// 中证指数
{
  "symbol": "CBA00642.CS",
  "date": "2015-09-09",
  "close": "118.9333",
  "update_time": "2026-05-29 15:21:30"
}

// 彭博指数 (估值数据)
{
  "symbol": "STAR50 Index",
  "date": "2024-01-02",
  "open": "952.4500",
  "high": "967.8900",
  "low": "950.1200",
  "close": "965.3400",
  "volume": 1234567890,
  "pe_ttm": "45.2300",
  "pb_lf": "3.8500",
  "update_time": "2026-05-29 10:32:21"
}
```

**同步的主要指数：**

| 彭博代码 | 说明 |
|----------|------|
| STAR50 Index | 科创50指数 |
| HSI Index | 恒生指数 |
| HSTECH Index | 恒生科技指数 |
| VIX Index | 波动率指数 |
| BCOMTR Index | 彭博大宗商品指数 |
| LEGATRUU Index | 彭博全球综合债券指数 |

---

### 4. prices_future - 期货价格表

存储DMA期货合约的价格数据。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| symbol | VARCHAR(20) | 合约代码 |
| underlying | VARCHAR(10) | 品种代码 |
| date | DATE | 交易日期 |
| open | DECIMAL(12,4) | 开盘价 |
| high | DECIMAL(12,4) | 最高价 |
| low | DECIMAL(12,4) | 最低价 |
| close | DECIMAL(12,4) | 收盘价 |
| settle | DECIMAL(12,4) | 结算价 |
| volume | BIGINT | 成交量 |
| amount | DECIMAL(20,4) | 成交金额 |
| open_interest | BIGINT | 持仓量 |
| basis | DECIMAL(12,4) | 基差 |
| update_time | TIMESTAMP | 更新时间 |

**示例数据：**

```json
// 股指期货历史数据
{
  "symbol": "IF1005",
  "underlying": "IF",
  "date": "2010-04-16",
  "open": "3450.0000",
  "high": "3488.0000",
  "low": "3413.2000",
  "close": "3415.6000",
  "settle": "3431.2000",
  "volume": 48988,
  "amount": "50538805320.0000",
  "open_interest": 2702,
  "update_time": "2026-05-28 14:34:56"
}
```

**数据映射说明：**

- `DMA_settle` / `HCTA_settle` 工作表 → `settle` 字段 (结算价)
- `DMA_last` 工作表 → `close` 字段 (最新价)
- `HCTA_volume` 工作表 → `volume` 字段 (成交量)
- `DMA_ltd` / `HCTA_ltd` 工作表 → `assets.delist_date` (第一通知日)

---

## 数据质量检查

脚本内置以下数据质量检查机制：

1. **一致性检查**：与数据库现有数据进行比对，检测不一致的数据点
2. **增量同步**：只同步新增数据（基于日期判断）
3. **冲突处理**：使用 `ON CONFLICT DO UPDATE` 自动更新重复数据

---

## 代码映射配置

在脚本中可通过 `SYMBOL_MAPPING` 配置彭博代码到内部代码的映射：

```python
SYMBOL_MAPPING = {
    'STAR50 Index': 'STAR50',
    'HSI Index': 'HSI',
    'HSTECH Index': 'HSTECH',
    'VIX Index': 'VIX',
    'CNH L160 Curncy': 'CNH',
    'USDCNY Curncy': 'USDCNY',
    'USDCNH Curncy': 'USDCNH',
}
```

---

## 日志输出

日志文件保存在 `logs/bloomberg_sync_YYYYMMDD.log`，包含：
- 文件读取状态
- 各工作表处理结果
- 数据质量检查结果
- 错误信息

## 注意事项

1. **文件路径**：确保 `Z:\每日更新\数据\彭博\bbg_data_new.xlsx` 可访问
2. **Excel格式**：工作表名称需与 `SYMBOL_CATEGORIES` 配置匹配
3. **数据格式**：日期列应为第一列，数据从第二列开始
4. **网络依赖**：Z盘为网络共享盘，需确保网络连接正常

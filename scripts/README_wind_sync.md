# 万得数据同步脚本 (sync_wind_data.py)

## 功能概述

从万得(Wind)终端同步市场数据到本地PostgreSQL数据库，支持增量同步和全量刷新模式。

### 同步数据类型

| 数据类型 | 万得API | 目标表 | 说明 |
|---------|---------|--------|------|
| 外汇汇率 | edb | fx_rates | 人民币汇率等 |
| 股票指数 | wsd/wss | prices_index | 各类指数行情 |
| ETF | wsd/wss | prices_etf | ETF基金行情 |
| 宏观指标 | edb | macro_indicators | 经济数据指标 |
| 场外基金 | wsd | prices_fund | 存储复权净值 |

### 配置来源

配置内嵌于 `scripts/wind_config.py`，无需外部配置文件。

## 运行方式

```bash
# 默认增量同步（同步昨日数据）
python scripts/sync_wind_data.py

# 全量刷新（强制同步所有历史数据）
python scripts/sync_wind_data.py --full-refresh

# 测试模式（只处理指定标的）
python scripts/sync_wind_data.py --test
```

### 运行时机

建议每日盘后 **16:30** 运行，此时万得数据已更新完毕。

---

## 涉及的数据库表

### 1. assets - 资产主表

存储所有可交易标的的基础信息。

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
| delist_date | DATE | 退市/到期日期 | - |
| multiplier | DECIMAL(10,4) | 合约乘数 | - |
| tick_size | DECIMAL(10,4) | 最小变动单位 | - |
| is_active | BOOLEAN | 是否可交易 | DEFAULT TRUE |
| update_time | TIMESTAMP | 更新时间 | DEFAULT CURRENT_TIMESTAMP |

**示例数据：**

```json
// 外汇资产
{
  "symbol": "M0000185",
  "underlying": "M0000185",
  "name": "美元/人民币汇率",
  "asset_class": "fx",
  "exchange": "WIND",
  "currency": "CNY",
  "is_active": true,
  "update_time": "2026-05-29 15:17:10"
}

// 股指期货
{
  "symbol": "IF2603",
  "underlying": "IF",
  "name": "IF2603",
  "asset_class": "future",
  "exchange": "CFFEX",
  "contract_month": "202603",
  "list_date": "2025-07-21",
  "delist_date": "2026-03-20",
  "multiplier": "300.0000",
  "tick_size": "0.2000",
  "is_active": true,
  "update_time": "2026-05-28 16:30:05"
}

// ETF
{
  "symbol": "0JGN.L",
  "underlying": "0JGN",
  "name": "罗素2000ETF",
  "asset_class": "etf",
  "exchange": "UNKNOWN",
  "is_active": true,
  "update_time": "2026-05-29 14:07:50"
}

// 指数
{
  "symbol": "XUBSR9TD Index",
  "underlying": "XUBSR9TD I",
  "name": "XUBSR9TD Index",
  "asset_class": "index",
  "exchange": "BLOOMBERG",
  "is_active": true,
  "update_time": "2026-05-29 10:32:21"
}
```

---

### 2. fx_rates - 汇率表

存储外汇汇率数据，主要来自万得 edb 接口。

**表结构：**

| 字段名 | 类型 | 说明 | 约束 |
|--------|------|------|------|
| symbol | VARCHAR(50) | 万得代码 | PRIMARY KEY (复合) |
| date | DATE | 日期 | PRIMARY KEY (复合) |
| spot_rate | DECIMAL(12,6) | 即期汇率 | - |
| update_time | TIMESTAMP | 更新时间 | DEFAULT CURRENT_TIMESTAMP |

**外键约束：**
- `symbol` → `assets(symbol)` ON DELETE CASCADE

**示例数据：**

```json
// 美元兑人民币
{
  "symbol": "M0000185",
  "date": "2005-12-31",
  "spot_rate": "8.070200",
  "update_time": "2026-05-29 15:17:10"
}

// 日元兑人民币
{
  "symbol": "M0000187",
  "date": "2005-12-31",
  "spot_rate": "1.040300",
  "update_time": "2026-05-29 15:17:14"
}
```

**万得代码映射：**

| 万得代码 | 货币对 | 说明 |
|----------|--------|------|
| M0000185 | CNY/USD | 人民币汇率指数相关 |
| M0000186 | EUR/CNY | 欧元兑人民币 |
| M0000187 | JPY/CNY | 日元兑人民币 |
| M0000188 | HKD/CNY | 港币兑人民币 |

---

### 3. prices_index - 指数价格表

存储各类股票指数的日频行情数据。

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
{
  "symbol": "CBA00642.CS",
  "date": "2015-09-09",
  "close": "118.9333",
  "update_time": "2026-05-29 15:21:30"
}
```

---

### 4. prices_etf - ETF价格表

存储ETF基金的价格数据。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| symbol | VARCHAR(20) | ETF代码 |
| date | DATE | 交易日期 |
| open | DECIMAL(12,4) | 开盘价 |
| high | DECIMAL(12,4) | 最高价 |
| low | DECIMAL(12,4) | 最低价 |
| close | DECIMAL(12,4) | 收盘价 |
| volume | BIGINT | 成交量 |
| amount | DECIMAL(20,4) | 成交金额 |
| update_time | TIMESTAMP | 更新时间 |

**示例数据：**

```json
{
  "symbol": "588000.SH",
  "date": "2020-12-03",
  "close": "1.4170",
  "update_time": "2026-05-29 15:21:17"
}
```

---

### 5. prices_fund - 场外基金净值表

存储场外开放式基金的每日净值数据。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| symbol | VARCHAR(20) | 基金代码 |
| date | DATE | 日期 |
| nav | DECIMAL(10,4) | 单位净值 |
| nav_adj | DECIMAL(10,4) | 复权净值（考虑分红拆分） |
| acc_nav | DECIMAL(10,4) | 累计净值 |
| purchase_status | VARCHAR(10) | 申购状态 |
| redeem_status | VARCHAR(10) | 赎回状态 |
| dividend | DECIMAL(10,4) | 分红金额 |
| split_ratio | DECIMAL(10,4) | 拆分比例 |
| update_time | TIMESTAMP | 更新时间 |

**示例数据：**

```json
{
  "symbol": "007994.OF",
  "date": "2024-01-02",
  "nav": "1.2345",
  "nav_adj": "1.4567",
  "acc_nav": "2.3456",
  "update_time": "2026-05-29 16:00:00"
}
```

**万得代码映射：**

| 万得代码 | 基金名称 | 说明 |
|----------|----------|------|
| 007994.OF | 中证500指数基金 | 跟踪中证500指数 |
| 110026.OF | 易方达安心回报债券 | 债券型基金 |
| 501018.SH | 南方原油 | 商品型基金 |

---

### 6. macro_indicators - 宏观经济指标表

存储宏观经济数据指标。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| indicator_code | VARCHAR(30) | 指标代码 |
| indicator_name | VARCHAR(100) | 指标名称 |
| date | DATE | 发布日期 |
| period_type | VARCHAR(10) | 周期(daily/weekly/monthly/quarterly/yearly) |
| value | DECIMAL(20,6) | 指标值 |
| value_yoy | DECIMAL(10,4) | 同比 |
| value_mom | DECIMAL(10,4) | 环比 |
| unit | VARCHAR(20) | 单位 |
| update_time | TIMESTAMP | 更新时间 |

**示例数据：**

```json
{
  "indicator_code": "10y_rate_cn",
  "indicator_name": "10y_rate_cn",
  "date": "2023-01-02",
  "period_type": "daily",
  "value": "2.480000",
  "unit": "%",
  "update_time": "2026-05-29 14:27:20"
}
```

---

## 数据质量检查

脚本内置以下数据质量检查机制：

1. **一致性检查**：重叠日期的数据与数据库现有数据进行比对
2. **异常波动检测**：检查价格是否出现超过10%的异常波动
3. **重复数据检测**：基于 (symbol, date) 复合主键防止重复插入

---

## 日志输出

日志文件保存在 `logs/wind_sync_YYYYMMDD.log`，包含：
- 同步开始/结束时间
- 每个标的的处理状态
- 数据质量检查结果
- 错误信息

## 注意事项

1. **Wind API 依赖**：运行前需确保已安装 WindPy 并登录万得终端
2. **数据库连接**：通过 `config.yaml` 配置数据库连接信息
3. **内存使用**：全量刷新模式会加载大量历史数据，注意内存占用

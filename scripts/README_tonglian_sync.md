# 通联期货数据同步脚本 (sync_tonglian_smart.py)

## 功能概述

从通联数据（DataYes）MySQL数据库同步中国期货市场的日频行情数据到本地PostgreSQL数据库。

### 同步数据类型

| 数据类型 | 来源表 | 目标表 | 说明 |
|---------|--------|--------|------|
| 期货合约日频行情 | `mkt_futd` | prices_future | 期货合约的OHLCV、持仓量等 |
| 合约信息 | `mkt_futurec` | assets | 合约基础信息（自动同步） |
| 交易日历 | `sys_calendar` | trade_calendar | 中国期货市场交易日历 |

### 覆盖品种

支持 **50+ 个期货品种**，包括：

**股指期货：**
- IF（沪深300）、IC（中证500）、IM（中证1000）、IH（上证50）

**国债期货：**
- T（10年期）、TF（5年期）、TS（2年期）、TL（30年期）

**贵金属：**
- AU（黄金）、AG（白银）

**有色金属：**
- CU（铜）、AL（铝）、ZN（锌）、PB（铅）、NI（镍）、SN（锡）

**黑色系：**
- RB（螺纹钢）、HC（热卷）、I（铁矿石）、J（焦炭）、JM（焦煤）

**农产品：**
- C（玉米）、M（豆粕）、Y（豆油）、P（棕榈油）、A（豆一）、B（豆二）

**化工品：**
- L（聚乙烯）、PP（聚丙烯）、PVC、TA（PTA）、MA（甲醇）、RU（橡胶）

**能源：**
- SC（原油）、FU（燃料油）、BU（沥青）、PG（LPG）

## 运行方式

```bash
# 默认增量同步（从上次同步日期到最新交易日）
python scripts/sync_tonglian_smart.py

# 强制全量刷新（重新同步所有历史数据）
python scripts/sync_tonglian_smart.py --full-refresh

# 同步特定品种
python scripts/sync_tonglian_smart.py --underlying RB

# 同步特定日期范围
python scripts/sync_tonglian_smart.py --start-date 2024-01-01 --end-date 2024-12-31
```

### 运行时机

建议每日盘后 **17:30** 运行，此时通联数据库已更新当日数据。

---

## 涉及的数据库表

### 1. assets - 资产主表

存储期货合约的基础信息，自动从通联同步。

**表结构：**

| 字段名 | 类型 | 说明 | 约束 |
|--------|------|------|------|
| symbol | VARCHAR(50) | 合约代码 | PRIMARY KEY |
| underlying | VARCHAR(10) | 品种代码 | NOT NULL |
| name | VARCHAR(100) | 合约名称 | - |
| asset_class | VARCHAR(20) | 资产类别 | 'future' |
| exchange | VARCHAR(10) | 交易所 | CFFEX/SHFE/DCE/CZCE/INE |
| currency | VARCHAR(3) | 币种 | CNY |
| contract_month | VARCHAR(6) | 合约月份 | 如 "2501" |
| list_date | DATE | 上市日期 | - |
| delist_date | DATE | 到期日期 | 最后交易日 |
| multiplier | DECIMAL(10,4) | 合约乘数 | - |
| tick_size | DECIMAL(10,4) | 最小变动单位 | - |
| is_active | BOOLEAN | 是否可交易 | TRUE/FALSE |
| update_time | TIMESTAMP | 更新时间 | - |

**示例数据：**

```json
// 沪深300股指期货
{
  "symbol": "IF2501",
  "underlying": "IF",
  "name": "IF2501",
  "asset_class": "future",
  "exchange": "CFFEX",
  "currency": "CNY",
  "contract_month": "202501",
  "list_date": "2024-11-25",
  "delist_date": "2025-01-17",
  "multiplier": "300.0000",
  "tick_size": "0.2000",
  "is_active": true,
  "update_time": "2026-05-29 17:30:05"
}

// 螺纹钢期货
{
  "symbol": "RB2501",
  "underlying": "RB",
  "name": "螺纹钢2501",
  "asset_class": "future",
  "exchange": "SHFE",
  "currency": "CNY",
  "contract_month": "202501",
  "list_date": "2024-01-16",
  "delist_date": "2025-01-15",
  "multiplier": "10.0000",
  "tick_size": "1.0000",
  "is_active": true,
  "update_time": "2026-05-29 17:30:05"
}
```

---

### 2. prices_future - 期货价格表

存储期货合约的日频行情数据。

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
| basis | DECIMAL(12,4) | 基差（预留） |
| update_time | TIMESTAMP | 更新时间 |

**主键：** (symbol, date)

**外键：** symbol → assets(symbol)

**示例数据：**

```json
{
  "symbol": "IF2501",
  "underlying": "IF",
  "date": "2026-01-15",
  "open": "3450.0000",
  "high": "3488.0000",
  "low": "3413.2000",
  "close": "3415.6000",
  "settle": "3431.2000",
  "volume": 123456,
  "amount": "12678901234.0000",
  "open_interest": 87654,
  "basis": null,
  "update_time": "2026-05-29 17:30:05"
}
```

---

### 3. trade_calendar - 交易日历表

存储中国期货市场交易日历。

**表结构：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | SERIAL | 主键 |
| date | DATE | 日期 |
| market | VARCHAR(10) | 市场代码 |
| is_trading_day | BOOLEAN | 是否交易日 |
| is_weekend | BOOLEAN | 是否周末 |
| is_holiday | BOOLEAN | 是否假日 |
| holiday_name | VARCHAR(50) | 假日名称 |

**示例数据：**

```json
{
  "id": 1,
  "date": "2026-01-01",
  "market": "CFFEX",
  "is_trading_day": false,
  "is_weekend": false,
  "is_holiday": true,
  "holiday_name": "元旦"
}
```

---

## 数据源配置

通联数据库连接配置在 `config.yaml` 中：

```yaml
tonglian:
  host: "your_tonglian_host"
  port: 3306
  user: "your_username"
  password: "your_password"
  database: "datayes"
  charset: "utf8mb4"
```

## 首次同步 vs 增量同步

### 首次同步
- 自动从品种上市日开始同步
- 使用 tqdm 进度条显示进度
- 50+ 个品种约需 10-30 分钟

### 增量同步
- 自动检测上次同步日期
- 只同步新增交易日数据
- 通常只需几秒到几分钟

## 数据质量检查

脚本内置以下检查：
1. **重复数据检测**：基于 (symbol, date) 复合主键
2. **价格合理性检查**：检测异常价格（如为0或负数）
3. **持仓量检查**：检测持仓量异常变化
4. **自动更新**：使用 `ON CONFLICT DO UPDATE` 自动修复错误数据

## 与其他脚本的关系

```
┌─────────────────────────────────────────────────────────────┐
│                    数据源对比                               │
├─────────────────────────────────────────────────────────────┤
│  通联同步              │  万得同步            │  彭博同步    │
│  (sync_tonglian_)      │  (sync_wind_)        │  (sync_blo..)│
├────────────────────────┼──────────────────────┼──────────────┤
│  期货价格              │  外汇/宏观/指数      │  指数/外汇   │
│  (prices_future)       │  (fx_rates/macro/..) │  (prices/..) │
├────────────────────────┴──────────────────────┴──────────────┤
│                      统一目标表                             │
│                    (prices_future)                          │
└─────────────────────────────────────────────────────────────┘
```

**注意：** 通联同步的期货数据与万得、彭博的数据在同一 `prices_future` 表中存储，可通过 `symbol` 区分。

## 常见问题

### 1. 连接失败
**错误：** `Failed to connect Tonglian database`

**原因：**
- 网络不通（需要连接内网通联服务器）
- 配置信息错误
- MySQL端口未开放

**解决：** 检查 `config.yaml` 中的通联配置和网络连接

### 2. 数据重复
**错误：** `duplicate key value violates unique constraint`

**解决：** 脚本已使用 `ON CONFLICT DO UPDATE`，此错误通常可忽略

### 3. 品种未找到
**警告：** `未知品种: XXX`

**原因：** 该品种不在 `UNDERLYING_START_DATES` 配置中

**解决：** 在脚本中添加品种的上市日期

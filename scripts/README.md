# 数据同步脚本目录

本目录包含QIS系统的数据同步脚本，用于从外部数据源（万得、彭博等）同步市场数据到本地PostgreSQL数据库。

## 脚本列表

| 脚本名 | 说明 | 数据源 | 运行时机 | 目标表 |
|--------|------|--------|----------|--------|
| [sync_wind_data.py](./sync_wind_data.py) | 万得数据同步 | Wind终端API | 每日16:30 | fx_rates, prices_index, prices_etf, macro_indicators |
| [sync_bloomberg_excel.py](./sync_bloomberg_excel.py) | 彭博Excel同步 | Z盘Excel文件 | 每日08:30 | prices_index, fx_rates, prices_future, assets |
| [sync_tonglian_smart.py](./sync_tonglian_smart.py) | 通联期货同步 | 通联MySQL | 每日17:30 | prices_future, assets, trade_calendar |
| [sync_logger.py](./sync_logger.py) | 日志配置模块 | - | - | - |
| [wind_config.py](./wind_config.py) | 万得配置数据 | - | - | - |

## 详细文档

- [万得同步脚本说明](./README_wind_sync.md)
- [彭博同步脚本说明](./README_bloomberg_sync.md)
- [通联同步脚本说明](./README_tonglian_sync.md)

## 数据库表概览

```
┌─────────────────────────────────────────────────────────────┐
│                         assets                              │
│  资产主表 - 存储所有标的的基础信息                          │
│  PK: symbol                                                 │
└──────────────┬──────────────────────────────────────────────┘
               │ 外键关联
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌──────────┐
│fx_rates│ │prices_*│ │macro_ind.│
│汇率数据│ │价格数据│ │ 宏观指标  │
└────────┘ └────────┘ └──────────┘
```

### 各表用途

| 表名 | 用途 | 数据来源 |
|------|------|----------|
| `assets` | 资产基础信息主表 | 万得/彭博/通联 |
| `fx_rates` | 外汇汇率数据 | 万得edb/彭博Excel |
| `prices_index` | 指数行情数据 | 万得wsd/彭博Excel |
| `prices_etf` | ETF基金价格 | 万得wsd |
| `prices_fund` | 场外基金净值 | 万得wsd |
| `prices_stock` | 个股价格(预留) | 万得wsd |
| `prices_future` | 期货合约价格 | 通联/彭博DMA/万得 |
| `prices_future_continuous` | 期货连续合约 | 系统计算 |
| `macro_indicators` | 宏观经济指标 | 万得edb |
| `trade_calendar` | 交易日历 | 通联 |

## 快速开始

### 1. 配置数据库连接

确保 `config.yaml` 中配置了正确的数据库连接信息：

```yaml
database:
  url: "postgresql://user:password@localhost:5432/qis_db"
```

### 2. 运行同步脚本

```bash
# 万得同步
python scripts/sync_wind_data.py

# 彭博同步
python scripts/sync_bloomberg_excel.py
```

### 3. 查看日志

```bash
# 查看最新日志
tail -f logs/wind_sync_$(date +%Y%m%d).log
tail -f logs/bloomberg_sync_$(date +%Y%m%d).log
```

## 特殊处理说明

### 场外基金（.OF后缀）处理逻辑

#### 什么是场外基金？

场外基金（Over-The-Counter Fund）是指**不在证券交易所上市交易**的基金产品，与ETF等场内基金相对。

**识别特征：**
- 代码后缀为 `.OF`（Open-end Fund）
- 交易场所是基金公司直销或代销渠道（银行、第三方平台）
- 无实时交易价格，每日只有一个净值（NAV）
- 交易日15:00收盘后计算当日净值

**配置中的场外基金示例：**

```python
# wind_config.py
{'分类': 'underlying_otc', 'tickers': '007994.OF', ...}  # 中证500指数基金
{'分类': 'underlying_otc', 'tickers': '110026.OF', ...}  # 易方达安心回报债券
{'分类': 'underlying_otc', 'tickers': '501018.SH', ...}  # 南方原油
```

#### 数据存储方式

场外基金净值存储到专门的 **`prices_fund`** 表：

**1. 数据特性差异**

| 特性 | 场内基金(ETF) | 场外基金(OF) |
|------|--------------|-------------|
| 存储表 | `prices_etf` | `prices_fund` |
| 交易价格 | 实时价格（OHLC） | 每日净值（NAV） |
| 数据频率 | 实时/分钟级 | 日频（每日一条） |
| 获取字段 | `close`（收盘价） | `NAV_adj`（复权净值） |
| 主键 | (symbol, date) | (symbol, date) |

**2. 代码实现**

```python
# sync_wind_data.py 中的处理逻辑
elif 'otc' in asset_type or ticker.endswith('.OF'):
    # 场外基金 -> prices_fund（存储净值）
    return ('prices_fund', 'symbol')
```

**3. 数据处理流程**

```
万得配置                      同步脚本                      数据库
┌──────────┐               ┌──────────────┐           ┌──────────────────┐
│007994.OF │  ───────────→ │ 识别为场外基金 │  ──────→ │ 写入assets表     │
│110026.OF │  ───────────→ │ (分类=underlying_otc)    │ (资产基础信息)    │
│501018.SH│               │             │           │                  │
└──────────┘               │ 存储净值数据  │  ──────→ │ 写入prices_fund  │
                           │ (nav_adj字段)│           │ (净值数据)        │
                           └──────────────┘           └──────────────────┘
```

**4. 表结构**

```sql
CREATE TABLE prices_fund (
    symbol VARCHAR(20) NOT NULL,     -- 基金代码
    date DATE NOT NULL,               -- 日期
    nav DECIMAL(10, 4),              -- 单位净值
    nav_adj DECIMAL(10, 4),          -- 复权净值
    acc_nav DECIMAL(10, 4),          -- 累计净值
    update_time TIMESTAMP            -- 更新时间
);
```

---

## 常见问题

### 1. 外键约束错误

**错误信息：** `ForeignKeyViolation: 键值对(symbol)=(XXX)没有在表"assets"中出现`

**原因：** 同步价格数据前，资产信息未先写入assets表。

**解决：** 脚本已自动处理，如仍报错请检查 `_ensure_asset_exists` 函数是否正常工作。

### 2. 字段不存在错误

**错误信息：** `UndefinedColumn: 字段 "xxx" 不存在`

**原因：** 表结构与代码不匹配。

**解决：** 
- 检查数据库表结构是否与 `database/schema.sql` 一致
- 如不一致，运行 `python database/init_tables.py` 更新表结构

### 3. CHECK约束错误

**错误信息：** `CheckViolation: 关系 "assets" 的新列违反了检查约束 "chk_asset_class"`

**原因：** `asset_class` 字段值不在允许的枚举范围内。

**解决：** 运行 `database/fix_fx_constraint.sql` 更新约束。

## 数据流向图

```
┌───────────────────────────────────────────────────────────────────────────┐
│                               外部数据源                                   │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ Wind终端    │  │ 彭博Excel   │  │ 通联MySQL   │  │ 其他数据源  │      │
│  │ w.wsd()     │  │ bbg_data    │  │ mkt_futd    │  │ (预留)      │      │
│  │ w.edb()     │  │ _new.xlsx   │  │ (期货数据)   │  │             │      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
└─────────┼────────────────┼────────────────┼────────────────┼──────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                               同步脚本层                                   │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │sync_wind    │  │sync_bloomberg│  │sync_tonglian│  │ sync_xxx    │       │
│  │_data.py     │  │_excel.py     │  │_smart.py    │  │ (预留)      │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
└─────────┼────────────────┼────────────────┼────────────────┼──────────────┘
          │                │                │                │
          └────────────────┴────────────────┴────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                               数据库层                                     │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   assets    │  │  fx_rates   │  │ prices_*    │  │ macro_ind.  │       │
│  │  (资产主表) │  │  (汇率数据) │  │ (价格数据)  │  │ (宏观指标)   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
└───────────────────────────────────────────────────────────────────────────┘
```

## 维护说明

### 添加新的同步标的

1. **万得数据源：** 修改 `wind_config.py` 中的配置DataFrame
2. **彭博数据源：** 修改 `sync_bloomberg_excel.py` 中的 `SYMBOL_CATEGORIES`
3. **通联数据源：** 修改 `sync_tonglian_smart.py` 中的 `UNDERLYING_START_DATES`

### 修改表结构

1. 编辑 `database/schema.sql`
2. 运行 `python database/init_tables.py`
3. 更新对应脚本的README文档

### 日志清理

日志文件按天分割，建议配置定时任务清理7天前的日志：

```bash
# 添加到crontab
0 0 * * * find logs/ -name "*.log" -mtime +7 -delete
```

## 联系支持

如有问题，请联系系统管理员或查看各脚本的详细README文档。

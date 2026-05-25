# QIS System - 量化投资策略系统

Quantitative Investment Strategy System - 支持多数据源、本地优先架构、期货展期策略、对冲组合管理的量化研究平台。

## 核心特性

- **本地优先架构**: 策略计算使用本地 PostgreSQL，盘后从多数据源同步
- **多数据源支持**: Wind、Tonglian MySQL、Swifquant、Bloomberg Excel
- **科学资产命名**: 支持连续合约命名 `{underlying}_{type}{p}q{q}_{price}[_vol]`
- **期货展期策略**: 支持双窗口展期 (p/q 参数控制)，静态/动态展期规则
- **统一数据接口**: DataManager 封装所有数据访问，自动处理数据源切换

## 项目结构

```
qis_system/
├── config/                      # 配置文件
│   ├── settings.py              # 主配置（Pydantic BaseSettings）
│   ├── assets.yaml              # 资产定义配置（110+ 期货/指数/ETF）
│   └── __init__.py
│
├── data/                        # 数据层
│   ├── base.py                  # 数据源基类 DataSourceBase
│   ├── data_manager.py          # 统一数据接口 DataManager
│   ├── cache.py                 # 本地数据缓存管理
│   │
│   ├── config/                  # 资产配置模型
│   │   ├── models.py            # AssetConfig, RollConfig 等数据类
│   │   └── loader.py            # YAML 配置加载器
│   │
│   ├── database/                # 数据库层（PostgreSQL）
│   │   ├── connection.py        # DatabaseConnection 连接管理
│   │   ├── managers/            # CRUD 管理器
│   │   │   ├── price_manager.py       # 股票价格/期货价格/指数价格
│   │   │   ├── strategy_manager.py    # 策略NAV、持仓、交易
│   │   │   ├── asset_manager.py       # 资产信息、交易日历
│   │   │   └── hedge_manager.py       # 对冲工具、合成指数
│   │   └── __init__.py          # DatabaseManager 主入口
│   │
│   ├── sync/                    # 数据同步模块
│   │   ├── tonglian_sync.py     # 同花顺 MySQL 同步
│   │   ├── wind_sync.py         # Wind 数据同步
│   │   ├── bbg_excel_sync.py    # Bloomberg Excel 导入
│   │   ├── continuous_builder.py# 连续合约构建
│   │   └── concat_builder.py    # 拼接资产构建
│   │
│   └── future_roll.py           # 期货展期计算
│
├── models/                      # 模型层
│   ├── allocation/              # 资产配置（Risk Parity, 均值方差）
│   ├── factor/                  # 多因子模型
│   └── option/                  # 期权定价（Black-Scholes, 希腊值）
│
├── strategies/                  # 策略层
│   ├── base.py                  # 策略基类
│   ├── allocation_strategy.py   # 资产配置策略
│   ├── cta_strategy.py          # CTA 策略
│   ├── etf_rotation_strategy.py # ETF 轮动
│   └── option_strategy.py       # 期权策略
│
├── backtest/                    # 回测引擎
│   ├── engine.py                # 回测引擎
│   ├── portfolio.py             # 组合管理
│   └── metrics.py               # 绩效分析
│
├── execution/                   # 执行层
│   └── paper_trading.py         # 模拟交易
│
├── scripts/                     # 执行脚本
│   ├── import_config.py         # 导入资产配置到数据库
│   ├── sync_daily.py            # 每日数据同步（手动执行）
│   └── sync_history.py          # 历史数据同步
│
├── research/                    # 研究示例
│   └── examples/
│       ├── test_data_manager.py # 数据管理器测试
│       ├── test_allocation.py   # 资产配置测试
│       └── test_option_strategies.py
│
├── tests/                       # 单元测试
├── alembic/                     # 数据库迁移
├── Makefile                     # 常用命令
└── .env.example                 # 环境变量模板
```

## 数据流架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Data Sources                        │
│  ┌───────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────────┐  │
│  │   Wind    │  │ Tonglian     │  │ Swifquant │  │ Bloomberg    │  │
│  │  (万得)   │  │ (同花顺)     │  │           │  │ Excel        │  │
│  └─────┬─────┘  └──────┬───────┘  └─────┬─────┘  └──────┬───────┘  │
└────────┼───────────────┼────────────────┼───────────────┼──────────┘
         │               │                │               │
         ▼               ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Sync Layer (盘后同步)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ wind_sync   │  │ tonglian_   │  │ swifquant_  │  │ bbg_excel_ │ │
│  │             │  │ sync        │  │ sync        │  │ sync       │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Local PostgreSQL (qis_db)                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ prices_stock │ │prices_future │ │prices_index  │ │ roll_configs│ │
│  ├──────────────┤ ├──────────────┤ ├──────────────┤ ├─────────────┤ │
│  │ prices_future│ │strategy_nav  │ │actual_       │ │ concat_     │ │
│  │ _continuous  │ │target_       │ │positions     │ │ asset_      │ │
│  │              │ │positions     │ │              │ │ configs     │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Strategy Layer (<10ms查询)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ DataManager │  │ 各类策略    │  │ 回测引擎    │  │ 绩效分析   │ │
│  │ .get_data() │  │             │  │             │  │            │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 填入你的配置
# - PostgreSQL 连接信息
# - Wind/Tonglian/Swifquant 数据源配置
```

### 2. 安装依赖

```bash
make install
# 或
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
# 创建数据库表
make db-init

# 或手动执行
python -c "from data.database import DatabaseManager; db = DatabaseManager(); db.create_tables()"
```

### 4. 导入资产配置

```bash
# 将 config/assets.yaml 导入数据库
python scripts/import_config.py
```

### 5. 同步历史数据

```bash
# 同步期货数据（同花顺）
python scripts/sync_history.py --source tonglian --type futures

# 同步指数数据（Wind）
python scripts/sync_history.py --source wind --type indices
```

### 6. 构建连续合约

```bash
# 构建期货连续合约
python -c "
from data.sync.continuous_builder import ContinuousContractBuilder
from data.database import DatabaseManager

db = DatabaseManager()
builder = ContinuousContractBuilder(db)

# 构建所有配置中的连续合约
builder.build_all_continuous_contracts()
"
```

## 使用示例

### 统一数据查询

```python
from data import DataManager

# DataManager 自动路由到本地数据库或远程数据源
dm = DataManager()

# 查询股票价格（优先本地，无数据则尝试远程）
df = dm.get_daily_price(
    symbol="000300.SH",
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# 查询期货连续合约
df = dm.get_future_continuous(
    underlying="IF",
    roll_start_days=10,   # p 参数：观察窗口开始
    roll_end_days=3       # q 参数：强制展期日
)

# 获取拼接资产（如 创业板指 + 创业板ETF）
df = dm.get_concat_asset("CYBZ_Splicing")
```

### 资产配置策略

```python
from data import DataManager
from models.allocation import RiskParityOptimizer
import pandas as pd

dm = DataManager()

# 获取资产数据
assets = ["000300.SH", "H00985.CSI", "AU.SHF", "CU.SHF"]
data = {a: dm.get_daily_price(a, start_date="2020-01-01") for a in assets}
prices = pd.DataFrame({k: v["close"] for k, v in data.items()})

# Risk Parity 优化
optimizer = RiskParityOptimizer()
weights = optimizer.optimize(prices.pct_change().dropna())
print(weights)
```

### 期货展期收益计算

```python
from data.future_roll import calculate_roll_return

# 计算展期收益因子
roll_return = calculate_roll_return(
    main_price=3500,      # 近月合约价格
    next_price=3520,      # 远月合约价格
    days_to_expiry=30     # 距离到期天数
)
# annualized_return = roll_return * (365 / days_to_expiry)
```

## 资产命名规范

### 期货连续合约命名

格式: `{underlying}_{type}{p}q{q}_{price}[_vol]`

示例:
- `IF_S7q4_settle` - IF静态展期(7天观察/4天强制)，结算价
- `IF_S7q4_close` - IF静态展期，收盘价
- `CU_D73q13_close_vol` - CU动态展期(73天/13天)，收盘价+成交量加权
- `RB_S10q3_settle` - RB静态展期(10天/3天)，结算价

### 拼接资产命名

格式: `{name}_Splicing`

示例:
- `CYBZ_Splicing` - 创业板指 (2010-06-01 前用创业板ETF拼接)
- `SP500_Splicing` - 标普500 (盘后+期货夜盘拼接)

## 常用命令

```bash
# 查看所有可用命令
make help

# 数据库操作
make db-init         # 初始化数据库表
make db-migrate MESSAGE="add new table"  # 创建迁移
make db-upgrade      # 应用迁移
make db-history      # 查看迁移历史

# 数据同步
make sync-daily      # 执行每日数据同步
make sync-config     # 导入资产配置

# 开发
make test            # 运行测试
make lint            # 代码检查
make format          # 格式化代码
make clean           # 清理缓存
```

## 配置说明

### assets.yaml 结构

```yaml
futures:
  - symbol: IF
    name: 沪深300股指期货
    exchange: CFFEX
    multiplier: 300
    roll_type: static
    roll_start_days: 7
    roll_end_days: 4
    active_months: [3, 6, 9, 12]

indices:
  - symbol: 000300.SH
    name: 沪深300
    exchange: SSE
    source: wind

concat_assets:
  - name: CYBZ_Splicing
    components:
      - symbol: 159915.SZ
        end_date: "2010-05-31"
      - symbol: 399006.SZ
        start_date: "2010-06-01"
```

## 郑商所合约代码规则

ZCE 使用1位年份，其他交易所使用2位年份：
- 郑商所: `TA409` (TA + 4 + 09)
- 大商所: `RB2409` (RB + 24 + 09)

系统在 `AssetConfig.get_contract_code()` 中自动处理此差异。

## 技术栈

- **Python 3.10+**
- **PostgreSQL**: 本地数据存储
- **SQLAlchemy**: ORM 和数据库操作
- **Alembic**: 数据库迁移
- **Pandas**: 数据处理
- **Pydantic**: 配置验证
- **Loguru**: 日志记录

## License

Private - 自用量化研究系统

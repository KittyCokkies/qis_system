# QIS System - Airflow 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- Windows 10/11 (WSL2) / Linux / macOS

## Python 版本

- Airflow: 2.8.3
- Python: 3.12 (与项目一致)

## 快速启动

### 1. 配置环境变量

```bash
cd airflow
cp .env.example .env
# 编辑 .env 配置数据库连接
```

### 2. 启动服务

**Windows:**
```cmd
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

### 3. 访问 UI

- URL: http://localhost:8080
- 用户名: `admin`
- 密码: `admin`

## DAG 说明

### sync_tonglian_futures_daily

**功能:** 每日同步通联期货数据

**调度:** 工作日 17:30

**任务流程:**
1. 获取配置的所有期货品种
2. 并行同步每个品种:
   - 导入合约详情（乘数、tick_size、上市日期等）
   - 同步日频价格数据
3. 汇总同步结果

**手动触发:**
```bash
# 触发今日同步
docker-compose exec airflow-webserver airflow dags trigger sync_tonglian_futures_daily

# 测试指定日期
docker-compose exec airflow-webserver airflow dags test sync_tonglian_futures_daily 2026-05-26
```

## 目录结构

```
airflow/
├── docker-compose.yml      # 服务配置
├── Dockerfile              # 镜像构建
├── .env.example            # 环境变量模板
├── start.bat / start.sh    # 启动脚本
├── README.md               # 本文件
├── dags/                   # DAG 定义（已同步）
│   └── sync_tonglian_futures.py
├── logs/                   # 日志（自动创建）
└── plugins/                # 插件（自动创建）
```

## 常用命令

```bash
# 查看日志
docker-compose logs -f airflow-scheduler

# 进入容器
docker-compose exec airflow-webserver bash

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 完全重置（删除数据）
docker-compose down -v
```

## 数据库连接

Airflow 使用两个数据库:
1. **内部数据库** (postgres:5433) - Airflow 元数据
2. **项目数据库** (host.docker.internal:5432) - QIS 业务数据

确保 Docker 可以访问到项目 PostgreSQL:
- Windows: 使用 `host.docker.internal`
- Linux: 可能需要改为实际 IP 或启用 `host.docker.internal`

## 故障排查

### DAG 未显示
```bash
docker-compose exec airflow-webserver airflow dags list
docker-compose exec airflow-webserver airflow dags trigger sync_tonglian_futures_daily
```

### 数据库连接失败
检查 `.env` 中的 `DATABASE_URL` 和通联配置是否正确。

### 日志查看
```bash
docker-compose logs -f
```

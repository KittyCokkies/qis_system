#!/bin/bash
# =============================================================================
# QIS System - Airflow 启动脚本 (Linux/Mac)
# =============================================================================

set -e

echo "[INFO] 正在启动 Airflow..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "[WARN] .env 文件不存在，正在从模板创建..."
    cp .env.example .env
    echo "[WARN] 请编辑 .env 文件配置数据库连接信息后重新运行"
    exit 1
fi

# 创建必要目录
mkdir -p logs dags plugins

# 启动服务
echo "[INFO] 启动 Docker Compose 服务..."
docker-compose up -d

echo ""
echo "[INFO] Airflow 启动成功！"
echo "[INFO] Web UI: http://localhost:8080"
echo "[INFO] 用户名: admin, 密码: admin"
echo ""
echo "[INFO] 常用命令："
echo "  查看日志: docker-compose logs -f"
echo "  停止服务: docker-compose down"
echo "  进入容器: docker-compose exec airflow-webserver bash"
echo "  测试 DAG: docker-compose exec airflow-webserver airflow dags test sync_tonglian_futures_daily 2026-05-26"
echo ""

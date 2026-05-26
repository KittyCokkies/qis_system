@echo off
chcp 65001 >nul
REM =============================================================================
REM QIS System - Airflow 启动脚本 (Windows)
REM =============================================================================

echo [INFO] 正在启动 Airflow...

REM 检查 .env 文件是否存在
if not exist .env (
    echo [WARN] .env 文件不存在，正在从模板创建...
    copy .env.example .env
    echo [WARN] 请编辑 .env 文件配置数据库连接信息后重新运行
    pause
    exit /b 1
)

REM 创建必要目录
if not exist logs mkdir logs
if not exist dags mkdir dags
if not exist plugins mkdir plugins

REM 启动服务
echo [INFO] 启动 Docker Compose 服务...
docker-compose up -d

if %ERRORLEVEL% neq 0 (
    echo [ERROR] 启动失败
    pause
    exit /b 1
)

echo.
echo [INFO] Airflow 启动成功！
echo [INFO] Web UI: http://localhost:8080
echo [INFO] 用户名: admin, 密码: admin
echo.
echo [INFO] 查看日志: docker-compose logs -f
echo [INFO] 停止服务: docker-compose down
echo.

pause

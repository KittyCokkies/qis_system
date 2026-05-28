@echo off
chcp 65001 >nul
echo ==========================================
echo 设置每日期货数据同步任务
echo 执行时间: 每天 16:30
echo ==========================================
echo.

:: 创建任务
schtasks /Create ^
    /TN "QIS_TonglianFuturesSync" ^
    /TR "F:\qis_system\.venv\Scripts\python.exe F:\qis_system\scripts\sync_tonglian_smart.py" ^
    /SC DAILY ^
    /ST 16:30 ^
    /RL LIMITED ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 任务创建成功！
    echo 任务名称: QIS_TonglianFuturesSync
    echo 执行时间: 每天 16:30
    echo 执行命令: python scripts/sync_tonglian_smart.py
    echo.
    echo 查看任务: schtasks /Query /TN QIS_TonglianFuturesSync
    echo 删除任务: schtasks /Delete /TN QIS_TonglianFuturesSync /F
) else (
    echo.
    echo 任务创建失败，请检查权限
    echo 请以管理员身份运行此脚本
)

pause

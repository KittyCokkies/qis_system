@echo off
chcp 65001 >nul
echo ==========================================
echo Setting up Tonglian Futures Auto Sync
echo Schedule: Every day at 16:30
echo ==========================================
echo.

echo Creating scheduled task...
schtasks /Create /TN "QIS_TonglianFuturesSync" /TR "F:\qis_system\run_sync.bat" /SC DAILY /ST 16:30 /RL LIMITED /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Task created!
    echo.
    echo Task Details:
    echo   - Name: QIS_TonglianFuturesSync
    echo   - Time: 16:30 daily
    echo   - Command: F:\qis_system\run_sync.bat
    echo   - Log: F:\qis_system\logs\sync_cron.log
    echo.
    echo Commands:
    echo   schtasks /Query /TN QIS_TonglianFuturesSync
    echo   schtasks /Delete /TN QIS_TonglianFuturesSync /F
    echo   schtasks /Run /TN QIS_TonglianFuturesSync
) else (
    echo.
    echo [ERROR] Failed to create task
    echo Please run as Administrator
)

echo.
pause

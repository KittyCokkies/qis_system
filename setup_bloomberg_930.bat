@echo off
chcp 65001 >nul
echo ==========================================
echo Setting up Bloomberg Excel Auto Sync
echo Schedule: Every day at 09:30
echo ==========================================
echo.

:: Delete old task if exists
schtasks /Delete /TN "QIS_BloombergSync" /F >nul 2>&1

:: Create new task at 09:30
echo Creating scheduled task at 09:30...
schtasks /Create /TN "QIS_BloombergSync" /TR "F:\qis_system\run_bloomberg_sync.bat" /SC DAILY /ST 09:30 /RL LIMITED /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Task created!
    echo.
    echo Task Details:
    echo   - Name: QIS_BloombergSync
    echo   - Time: 09:30 daily
    echo   - Command: F:un_bloomberg_sync.bat
    echo   - Log: F:un_bloomberg_sync.bat
    echo.
    echo Commands:
    echo   schtasks /Query /TN QIS_BloombergSync
    echo   schtasks /Delete /TN QIS_BloombergSync /F
) else (
    echo.
    echo [ERROR] Failed to create task
    echo Please run as Administrator
)

echo.
pause

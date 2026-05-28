@echo off
chcp 65001 >nul
cd /d F:\qis_system

echo [%date% %time%] Starting Tonglian futures sync...

F:\qis_system\.venv\Scripts\python.exe scripts\sync_tonglian_smart.py >> logs\sync_cron.log 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] Sync completed successfully
) else (
    echo [%date% %time%] Sync failed with error code %ERRORLEVEL%
)

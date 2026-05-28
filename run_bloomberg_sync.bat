@echo off
chcp 65001 >nul
cd /d F:\qis_system

echo [%date% %time%] Starting Bloomberg Excel sync...

F:\qis_system\.venv\Scripts\python.exe scripts\sync_bloomberg_excel.py >> logs\sync_bloomberg_cron.log 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] Bloomberg sync completed successfully
) else (
    echo [%date% %time%] Bloomberg sync failed with error code %ERRORLEVEL%
)

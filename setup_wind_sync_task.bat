@echo off
chcp 65001 >nul

:: 设置万得数据同步定时任务
:: 运行时间: 每天下午 16:30

echo ============================================
echo 万得数据同步定时任务设置
echo ============================================
echo.

:: 删除旧任务（如果存在）
schtasks /delete /tn "QIS\Sync Wind Data" /f >nul 2>&1

:: 创建新任务
echo 正在创建定时任务...

schtasks /create ^
  /tn "QIS\Sync Wind Data" ^
  /tr "'F:\qis_system\venv\Scripts\python.exe' 'F:\qis_system\scripts\sync_wind_data.py'" ^
  /sc daily ^
  /st 16:30 ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /description "万得数据每日同步任务，下午16:30运行，同步外汇、宏观指标、ETF、指数等数据"

if %errorlevel% == 0 (
    echo.
    echo ============================================
    echo 定时任务创建成功！
    echo ============================================
    echo 任务名称: QIS\Sync Wind Data
    echo 运行时间: 每天 16:30
    echo 执行脚本: F:\qis_system\scripts\sync_wind_data.py
    echo.
    echo 查看任务: schtasks /query /tn "QIS\Sync Wind Data" /fo list
    echo 手动运行: schtasks /run /tn "QIS\Sync Wind Data"
    echo 删除任务: schtasks /delete /tn "QIS\Sync Wind Data" /f
    echo ============================================
) else (
    echo.
    echo [错误] 定时任务创建失败！
    echo 请检查是否以管理员身份运行此脚本
)

pause

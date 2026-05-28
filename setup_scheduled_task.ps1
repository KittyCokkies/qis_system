# PowerShell script to setup scheduled task for Tonglian data sync
# Run as Administrator

$TaskName = "TonglianFuturesSync"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -Command `
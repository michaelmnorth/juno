# Registers the Juno bridge to start hidden at logon, with a check every 5 minutes that restarts it if it has stopped.
# The bridge exits at once if a copy is already running, so the repeat check cannot create a second bot.
$root = Split-Path -Parent $PSScriptRoot
$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "$root\.venv\Scripts\pythonw.exe" -Argument "gateway\slack_bridge.py" -WorkingDirectory $root
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Juno Slack Bridge" -Action $action -Trigger @($atLogon, $watchdog) -Settings $settings -Principal $principal -Force | Out-Null
Get-ScheduledTask -TaskName "Juno Slack Bridge" | Select-Object TaskName, State | Format-List

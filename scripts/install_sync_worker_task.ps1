# Run explicitly to install automatic worker startup for the current Windows user.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$workerPath = Join-Path $projectRoot 'worker.py'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the project .venv first.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $workerPath + '"') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'NocDashboardSyncWorker' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'One dedicated NOC sync and alert worker; starts at user logon and restarts after failures.'
Write-Output 'Worker task installed. Start it with Start-ScheduledTask -TaskName NocDashboardSyncWorker.'

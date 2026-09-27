# Windows 작업 스케줄러에 등록: 로그온 시 자동으로 프로그램 시작 (창 없이 백그라운드).
# 실행:  PowerShell 에서  .\scripts\register_task.ps1
# 해제:  Unregister-ScheduledTask -TaskName "ThreadsAutoPost" -Confirm:$false

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { $pythonw = (Get-Command python).Source }

$action  = New-ScheduledTaskAction -Execute $pythonw -Argument "-m app.main" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable

Register-ScheduledTask -TaskName "ThreadsAutoPost" -Action $action -Trigger $trigger -Settings $settings -Description "Threads 자동 게시 (스케줄러 + 대시보드)" -Force | Out-Null

Write-Host "등록 완료: 작업 스케줄러 > ThreadsAutoPost"
Write-Host "지금 바로 시작하려면:  Start-ScheduledTask -TaskName ThreadsAutoPost"
Write-Host "대시보드: http://127.0.0.1:5000"

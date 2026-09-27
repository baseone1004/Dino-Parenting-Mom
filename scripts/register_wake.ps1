# 잠자기(절전) 상태에서도 게시 시각에 컴퓨터를 깨워 글이 올라가게 하는 등록 스크립트.
#
# 실행 방법: PowerShell 을 "관리자 권한으로 실행" 후
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\scripts\register_wake.ps1
#
# 하는 일:
#   1) 로그온 시 프로그램 자동 시작 (ThreadsAutoPost)
#   2) 게시 시각 3분 전마다 컴퓨터 깨우기 (ThreadsAutoWake-*) — 깨어나면 프로그램이 밀린 게시를 바로 처리
#   3) 전원 옵션에서 "절전 모드 해제 타이머 허용"
#   4) 전원 연결 시 잠자기 30분 (화면만 꺼지고 컴퓨터는 필요할 때 깨어남)
#
# 해제: .\scripts\register_wake.ps1 -Remove

param([switch]$Remove)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if ($Remove) {
  Get-ScheduledTask | Where-Object { $_.TaskName -like "ThreadsAuto*" } | Unregister-ScheduledTask -Confirm:$false
  Write-Host "ThreadsAuto* 작업 모두 해제됨"
  exit 0
}

# ---- config.yaml 에서 게시 시각 읽기 ----
$times = @()
foreach ($line in Get-Content "$root\config.yaml" -Encoding UTF8) {
  if ($line -match '^\s*times:\s*\[(.+)\]') {
    $times = ($Matches[1] -split ',') | ForEach-Object { $_.Trim().Trim('"').Trim("'") }
    break
  }
}
if (-not $times) { $times = @("08:00", "12:30", "21:00") }

# ---- 1) 로그온 시 프로그램 자동 시작 ----
$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { $pythonw = (Get-Command python).Source }
$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "-m app.main" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "ThreadsAutoPost" -Action $action -Trigger $trigger -Settings $settings -Description "Threads 자동 게시 (스케줄러 + 대시보드)" -Force | Out-Null
Write-Host "[1/4] 로그온 시 자동 시작 등록: ThreadsAutoPost"

# ---- 2) 게시 시각 3분 전 깨우기 ----
foreach ($t in $times) {
  $hh, $mm = $t.Split(':')
  $at = (Get-Date -Hour ([int]$hh) -Minute ([int]$mm) -Second 0).AddMinutes(-3)
  $wakeAction  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit"
  $wakeTrigger = New-ScheduledTaskTrigger -Daily -At $at
  $wakeSettings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
  $name = "ThreadsAutoWake-" + $t.Replace(':', '')
  Register-ScheduledTask -TaskName $name -Action $wakeAction -Trigger $wakeTrigger -Settings $wakeSettings -Description "게시 시각 전 컴퓨터 깨우기" -Force | Out-Null
  Write-Host "[2/4] 깨우기 등록: $name ($($at.ToString('HH:mm')))"
}

# ---- 3) 절전 해제 타이머 허용 (AC/배터리 모두) ----
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 | Out-Null
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 | Out-Null
powercfg /SETACTIVE SCHEME_CURRENT | Out-Null
Write-Host "[3/4] 절전 해제 타이머 허용"

# ---- 4) 전원 연결 시: 화면 10분 후 끄기, 잠자기 30분 후 (배터리는 기본값 유지) ----
powercfg /CHANGE monitor-timeout-ac 10 | Out-Null
powercfg /CHANGE standby-timeout-ac 30 | Out-Null
Write-Host "[4/4] 전원 연결 시 화면 10분 / 잠자기 30분"

Write-Host ""
Write-Host "완료. 이제 컴퓨터를 '종료'하지 말고 '절전'(또는 그냥 두기)으로 두세요."
Write-Host "게시 시각 3분 전에 자동으로 깨어나 글을 올리고, 30분 뒤 다시 잠듭니다."
Write-Host "지금 프로그램을 자동 시작으로 켜려면:  Start-ScheduledTask -TaskName ThreadsAutoPost"

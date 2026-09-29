# 내 PC → 서버로 프로젝트 전체(예약 글 DB·토큰·설정 포함) 복사 후 서비스 재시작.
#   .\scripts\deploy.ps1 -Server 1.2.3.4 -Key "$HOME\Downloads\LightsailDefaultKey-ap-northeast-2.pem"
#   처음 한 번은 -Setup 을 붙이면 서버 초기 설치까지 실행:
#   .\scripts\deploy.ps1 -Server 1.2.3.4 -Key "...pem" -Setup
param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$Key,
  [string]$User = "ubuntu",
  [string]$Remote = "/home/ubuntu/threads-auto",
  [switch]$Setup,
  # 서버 DB가 운영 원본이다. 재해복구처럼 명시적으로 필요한 경우에만 로컬 data/를 전송한다.
  [switch]$IncludeData
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ssh = "ssh -i `"$Key`" -o StrictHostKeyChecking=accept-new $User@$Server"

# pem 권한 정리 (Windows OpenSSH 는 키 파일이 너무 열려 있으면 거부)
icacls $Key /inheritance:r /grant:r "$($env:USERNAME):R" | Out-Null

Write-Host "== 서버 폴더 준비"
Invoke-Expression "$ssh `"mkdir -p $Remote/data $Remote/logs`""

Write-Host "== 파일 복사 (운영 DB·logs·.venv·__pycache__ 제외)"
$tmp = Join-Path $env:TEMP "threads-auto-deploy"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory $tmp | Out-Null
robocopy $root $tmp /E /XD data logs .venv __pycache__ .claude /XF "*.pyc" "console.log" "console.err" | Out-Null
if ($IncludeData) {
  Write-Host "경고: -IncludeData 지정됨 — 로컬 data/를 서버에 전송합니다."
  robocopy "$root\data" "$tmp\data" /E /XF "*.backup*" | Out-Null
}
scp -i "$Key" -o StrictHostKeyChecking=accept-new -r "$tmp\*" "${User}@${Server}:$Remote/"
Remove-Item $tmp -Recurse -Force

if ($Setup) {
  Write-Host "== 서버 초기 설치 (5분쯤)"
  Invoke-Expression "$ssh `"sed -i 's/\r$//' $Remote/scripts/server_setup.sh && bash $Remote/scripts/server_setup.sh`""
} else {
  Write-Host "== 서비스 재시작"
  Invoke-Expression "$ssh `"sudo systemctl restart threads-auto && sleep 3 && sudo systemctl is-active threads-auto`""
}
Write-Host "완료. 대시보드: http://${Server}:5000"

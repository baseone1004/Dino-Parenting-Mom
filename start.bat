@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem 이미 실행 중이면(포트 5000 사용 중) 대시보드만 브라우저로 연다
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
  echo 프로그램이 이미 실행 중입니다. 대시보드를 엽니다...
  start "" http://127.0.0.1:5000
  timeout /t 2 >nul
  exit /b 0
)

echo 프로그램 시작 중... (이 창을 닫으면 자동 게시가 멈춥니다)
start "" /min cmd /c "timeout /t 4 >nul && start http://127.0.0.1:5000"
python -m app.main
pause

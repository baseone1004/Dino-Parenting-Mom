#!/usr/bin/env bash
# Ubuntu 22.04/24.04 서버 초기 설정 — 프로젝트를 /home/ubuntu/threads-auto 에 올린 뒤 실행.
#   bash scripts/server_setup.sh
# 하는 일: 시간대(서울) · Python/Node 설치 · Claude Code 설치 · 의존성 설치 · systemd 서비스 등록(부팅 시 자동 시작)
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"

echo "== [1/6] 시간대: Asia/Seoul"
sudo timedatectl set-timezone Asia/Seoul

echo "== [2/6] 패키지 설치 (python3, pip, venv, curl, git)"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip curl git ca-certificates fonts-nanum

echo "== [3/6] Node.js 22 + Claude Code"
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs
fi
sudo npm install -g @anthropic-ai/claude-code >/dev/null 2>&1 || sudo npm install -g @anthropic-ai/claude-code

echo "== [4/6] Python 가상환경 + 의존성"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p data logs

echo "== [5/6] 1GB 서버용 스왑 2GB (없으면 생성)"
if ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== [6/6] systemd 서비스 등록 (threads-auto)"
sudo tee /etc/systemd/system/threads-auto.service >/dev/null <<EOF
[Unit]
Description=Threads auto posting (scheduler + dashboard)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=Asia/Seoul
Environment=PATH=${APP_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=${APP_DIR}/.venv/bin/python -m app.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable threads-auto >/dev/null

cat <<'MSG'

설치 완료.
다음 단계:
  1) Claude Code 로그인 (구독 사용, 한 번만):   claude
     → 브라우저 URL 이 나오면 열어서 로그인 → 코드 복사 → 터미널에 붙여넣기
     (API 키를 쓸 거면 .env 의 ANTHROPIC_API_KEY 와 config.yaml 의 ai.backend: api)
  2) 서비스 시작:   sudo systemctl start threads-auto
  3) 상태 확인:     sudo systemctl status threads-auto --no-pager
     로그:          tail -f logs/app.log
  4) 대시보드:      http://<서버IP>:5000  (아이디 admin / config.yaml 의 dashboard.password)
MSG

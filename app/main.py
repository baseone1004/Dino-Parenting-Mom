"""엔트리포인트: 스케줄러 + 대시보드 동시 기동.

    python -m app.main
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging
from logging.handlers import RotatingFileHandler

from app import store, scheduler
from app.config import cfg, LOG_DIR
from app.dashboard import run as run_dashboard


def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, sh])
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def main():
    setup_logging()
    store.init()
    scheduler.start()
    d = cfg["dashboard"]
    print(f"\n  대시보드: http://{d.get('host','127.0.0.1')}:{d.get('port',5000)}\n  종료: Ctrl+C\n")
    run_dashboard()


if __name__ == "__main__":
    main()

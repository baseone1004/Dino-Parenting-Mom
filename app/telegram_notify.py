"""텔레그램 알림. TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없으면 조용히 무시."""
from __future__ import annotations

import logging

import requests

from app.config import env

log = logging.getLogger("telegram")


def send(text: str):
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"텔레그램 알림 실패: {e}")

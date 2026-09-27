"""config.yaml + .env 로딩. 어디서든 `from app.config import cfg, ROOT` 로 접근."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
ACCOUNTS_DIR = ROOT / "accounts"
CONFIG_PATH = ROOT / "config.yaml"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")


def load() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        c = yaml.safe_load(f) or {}
    c.setdefault("ai", {})
    c.setdefault("posting", {})
    c.setdefault("coupang", {})
    c.setdefault("toss", {})
    c.setdefault("facebook", {})
    c.setdefault("instagram", {})
    c.setdefault("trend", {})
    c.setdefault("dashboard", {})
    c.setdefault("accounts", [])
    c.setdefault("token_warn_days", 7)
    return c


cfg = load()


def reload() -> dict:
    global cfg
    cfg = load()
    return cfg


def account_cfg(account_id: str) -> dict | None:
    for a in cfg["accounts"]:
        if a.get("id") == account_id:
            return a
    return None


def enabled_accounts() -> list[dict]:
    return [a for a in cfg["accounts"] if a.get("enabled", True)]


def account_dir(account_id: str) -> Path:
    return ACCOUNTS_DIR / account_id


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

"""SQLite 저장소. 초안/게시 이력, 계정 토큰, 주제 커서, 설정, 글감 후보."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, date

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "app.db"
_lock = threading.RLock()

# 게시 상태 (영상의 대시보드 항목과 동일)
DRAFT = "draft"          # 초안
SCHEDULED = "scheduled"  # 예약 대기 (다음 스케줄 시각에 게시)
PUBLISHED = "published"  # 게시 완료
FAILED = "failed"        # 실패

STATUS_LABEL = {DRAFT: "초안", SCHEDULED: "예약 대기", PUBLISHED: "게시 완료", FAILED: "실패"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    threads_user_id TEXT,
    username TEXT,
    access_token TEXT,
    token_expires_at TEXT,
    facebook_page_id TEXT,
    facebook_page_token TEXT,
    facebook_page_name TEXT,
    instagram_business_id TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    topic TEXT,
    body TEXT NOT NULL,
    link TEXT,
    status TEXT NOT NULL,
    threads_post_id TEXT,
    facebook_post_id TEXT,
    facebook_error TEXT,
    instagram_post_id TEXT,
    instagram_error TEXT,
    card_image_urls TEXT,
    product_url TEXT,
    product_image_url TEXT,
    body_formal TEXT,
    error TEXT,
    attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    published_at TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    insights_at TEXT
    ,publishing INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts_acc_status ON posts(account_id, status);
CREATE TABLE IF NOT EXISTS topic_cursor (
    account_id TEXT PRIMARY KEY,
    idx INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    title TEXT NOT NULL,
    angle TEXT,
    product TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    account_id TEXT,
    message TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # 기존 DB 마이그레이션 (없는 컬럼 추가)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(posts)")}
        for col, ddl in [("views", "INTEGER DEFAULT 0"), ("likes", "INTEGER DEFAULT 0"),
                         ("replies", "INTEGER DEFAULT 0"), ("reposts", "INTEGER DEFAULT 0"), ("insights_at", "TEXT"),
                         ("facebook_post_id", "TEXT"), ("facebook_error", "TEXT"),
                         ("instagram_post_id", "TEXT"), ("instagram_error", "TEXT"), ("card_image_urls", "TEXT"),
                         ("product_url", "TEXT"), ("product_image_url", "TEXT"), ("body_formal", "TEXT"),
                         ("publishing", "INTEGER DEFAULT 0")]:
            if col not in cols:
                c.execute(f"ALTER TABLE posts ADD COLUMN {col} {ddl}")
        # 프로세스가 강제 종료된 경우 남은 잠금을 시작 시 안전하게 해제한다.
        c.execute("UPDATE posts SET publishing=0 WHERE publishing<>0")
        acc_cols = {r["name"] for r in c.execute("PRAGMA table_info(accounts)")}
        for col, ddl in [("facebook_page_id", "TEXT"), ("facebook_page_token", "TEXT"),
                         ("facebook_page_name", "TEXT"), ("instagram_business_id", "TEXT")]:
            if col not in acc_cols:
                c.execute(f"ALTER TABLE accounts ADD COLUMN {col} {ddl}")


# ---------------- settings ----------------
def get_setting(key: str, default: str | None = None) -> str | None:
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key: str, value: str):
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------------- accounts ----------------
def get_account(account_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return dict(r) if r else None


def upsert_account(account_id: str, **fields):
    fields["updated_at"] = now()
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
    with conn() as c:
        c.execute(
            f"INSERT INTO accounts(id,{cols}) VALUES(?,{marks}) ON CONFLICT(id) DO UPDATE SET {updates}",
            (account_id, *fields.values()),
        )


# ---------------- posts ----------------
def add_post(account_id: str, topic: str, body: str, link: str | None, status: str,
            product_url: str | None = None, product_image_url: str | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO posts(account_id,topic,body,link,status,product_url,product_image_url,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (account_id, topic, body, link, status, product_url, product_image_url, now()),
        )
        return cur.lastrowid


def get_post(post_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(r) if r else None


def recent_instagram_duplicate(post_id: int, account_id: str, body: str,
                               hours: int = 24) -> dict | None:
    """같은 계정·같은 본문이 최근에 이미 Instagram에 게시됐는지 확인한다."""
    with conn() as c:
        r = c.execute(
            "SELECT id, instagram_post_id FROM posts "
            "WHERE id<>? AND account_id=? AND body=? AND instagram_post_id IS NOT NULL "
            "AND created_at >= datetime('now','localtime',?) ORDER BY id DESC LIMIT 1",
            (post_id, account_id, body, f"-{max(1, hours)} hours"),
        ).fetchone()
        return dict(r) if r else None


def update_post(post_id: int, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE posts SET {sets} WHERE id=?", (*fields.values(), post_id))


def claim_post(post_id: int) -> bool:
    """한 프로세스만 게시를 시작하도록 원자적으로 상태를 선점한다."""
    with conn() as c:
        cur = c.execute(
            "UPDATE posts SET publishing=1 WHERE id=? AND COALESCE(publishing,0)=0",
            (post_id,),
        )
        return cur.rowcount == 1


def release_post(post_id: int):
    with conn() as c:
        c.execute("UPDATE posts SET publishing=0 WHERE id=?", (post_id,))


def delete_post(post_id: int):
    with conn() as c:
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))


def list_posts(account_id: str | None = None, status: str | None = None, limit: int = 100,
               order: str = "recent") -> list[dict]:
    q, args = "SELECT * FROM posts WHERE 1=1", []
    if account_id:
        q += " AND account_id=?"
        args.append(account_id)
    if status:
        q += " AND status=?"
        args.append(status)
    q += " ORDER BY views DESC, id DESC LIMIT ?" if order == "views" else " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def next_scheduled(account_id: str) -> dict | None:
    with conn() as c:
        r = c.execute(
            "SELECT * FROM posts WHERE account_id=? AND status=? ORDER BY id ASC LIMIT 1",
            (account_id, SCHEDULED),
        ).fetchone()
        return dict(r) if r else None


def published_recent(account_id: str, days: int = 30) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM posts WHERE account_id=? AND status=? AND threads_post_id IS NOT NULL "
            "AND published_at >= datetime('now','localtime',?) ORDER BY id DESC",
            (account_id, PUBLISHED, f"-{days} days"))]


def top_posts(account_id: str, n: int = 3) -> list[dict]:
    """조회수 상위 글 (학습 예시용). 조회수 0인 글은 제외."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM posts WHERE account_id=? AND status=? AND views > 0 ORDER BY views DESC LIMIT ?",
            (account_id, PUBLISHED, n))]


def published_today(account_id: str) -> int:
    today = date.today().strftime("%Y-%m-%d")
    with conn() as c:
        r = c.execute(
            "SELECT COUNT(*) n FROM posts WHERE account_id=? AND status=? AND published_at LIKE ?",
            (account_id, PUBLISHED, today + "%"),
        ).fetchone()
        return r["n"]


def stats() -> dict:
    """전체 + 계정별 상태 카운트."""
    out = {"total": {s: 0 for s in STATUS_LABEL}, "by_account": {}}
    with conn() as c:
        for r in c.execute("SELECT account_id, status, COUNT(*) n FROM posts GROUP BY account_id, status"):
            out["total"][r["status"]] = out["total"].get(r["status"], 0) + r["n"]
            out["by_account"].setdefault(r["account_id"], {s: 0 for s in STATUS_LABEL})[r["status"]] = r["n"]
    return out


# ---------------- topic cursor ----------------
def get_cursor(account_id: str) -> int:
    with conn() as c:
        r = c.execute("SELECT idx FROM topic_cursor WHERE account_id=?", (account_id,)).fetchone()
        return r["idx"] if r else 0


def set_cursor(account_id: str, idx: int):
    with conn() as c:
        c.execute(
            "INSERT INTO topic_cursor(account_id,idx) VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET idx=excluded.idx",
            (account_id, idx),
        )


# ---------------- ideas (글감) ----------------
def add_idea(account_id: str, title: str, angle: str | None, product: str | None, source: str | None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO ideas(account_id,title,angle,product,source,created_at) VALUES(?,?,?,?,?,?)",
            (account_id, title, angle, product, source, now()),
        )
        return cur.lastrowid


def list_ideas(account_id: str | None = None, status: str = "pending") -> list[dict]:
    q, args = "SELECT * FROM ideas WHERE status=?", [status]
    if account_id:
        q += " AND account_id=?"
        args.append(account_id)
    q += " ORDER BY id DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def set_idea_status(idea_id: int, status: str):
    with conn() as c:
        c.execute("UPDATE ideas SET status=? WHERE id=?", (status, idea_id))


def pop_approved_idea(account_id: str) -> dict | None:
    """승인된 글감 하나를 꺼내 'used' 로 바꾸고 반환."""
    with conn() as c:
        r = c.execute(
            "SELECT * FROM ideas WHERE account_id=? AND status='approved' ORDER BY id ASC LIMIT 1", (account_id,)
        ).fetchone()
        if not r:
            return None
        c.execute("UPDATE ideas SET status='used' WHERE id=?", (r["id"],))
        return dict(r)


# ---------------- logs ----------------
def log(level: str, message: str, account_id: str | None = None):
    with conn() as c:
        c.execute("INSERT INTO logs(ts,level,account_id,message) VALUES(?,?,?,?)", (now(), level, account_id, message))
        c.execute("DELETE FROM logs WHERE id < (SELECT MAX(id) FROM logs) - 2000")


def recent_logs(limit: int = 50) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))]

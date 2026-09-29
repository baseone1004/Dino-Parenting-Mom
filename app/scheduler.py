"""APScheduler: 계정별 게시 슬롯, 토큰 자동 갱신, 글감 수집."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import service, store, trend
from app.config import cfg, enabled_accounts

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def build() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="Asia/Seoul", job_defaults={"misfire_grace_time": 3600, "coalesce": True})
    jitter = int(cfg["posting"].get("jitter_minutes", 0)) * 60
    times = cfg["posting"].get("times") or ["09:00", "14:00", "20:00"]

    for acc in enabled_accounts():
        for t in times:
            hh, mm = t.split(":")
            sched.add_job(
                service.run_slot, CronTrigger(hour=int(hh), minute=int(mm), jitter=jitter or None),
                args=[acc["id"]], id=f"slot-{acc['id']}-{t}", name=f"{acc['id']} {t}", replace_existing=True,
            )

    # 매일 03:30 토큰 만료 점검/갱신
    sched.add_job(service.refresh_expiring_tokens, CronTrigger(hour=3, minute=30), id="token-refresh", name="토큰 만료 점검", replace_existing=True)

    # 첫 게시 전에 계정별 오늘의 인기 상품을 한 번만 준비 (API 호출 제한 보호)
    sched.add_job(service.refresh_daily_products, CronTrigger(hour=7, minute=30), id="daily-products",
                  name="오늘의 인기 상품 선정", replace_existing=True)

    # 성과 측정 (조회수/좋아요/댓글)
    ins = cfg.get("insights") or {}
    if ins.get("enabled", True) and ins.get("cron"):
        sched.add_job(service.refresh_insights, CronTrigger.from_crontab(ins["cron"]), id="insights",
                      name="성과 측정", replace_existing=True)

    # 글감 수집
    tr = cfg["trend"]
    if tr.get("enabled", True) and tr.get("cron"):
        for acc in enabled_accounts():
            sched.add_job(trend.collect, CronTrigger.from_crontab(tr["cron"]), args=[acc["id"]],
                          id=f"trend-{acc['id']}", name=f"{acc['id']} 글감 수집", replace_existing=True)
    return sched


def start() -> BackgroundScheduler:
    global _scheduler
    _scheduler = build()
    _scheduler.start()
    jobs = ", ".join(j.name or j.id for j in _scheduler.get_jobs())
    store.log("INFO", f"스케줄러 시작: {jobs}")
    log.info("scheduler started: %s", jobs)
    return _scheduler


def get() -> BackgroundScheduler | None:
    return _scheduler


def next_runs() -> list[dict]:
    if not _scheduler:
        return []
    out = []
    for j in _scheduler.get_jobs():
        out.append({"id": j.id, "name": j.name or j.id,
                    "next": j.next_run_time.strftime("%m-%d %H:%M") if j.next_run_time else "-"})
    return sorted(out, key=lambda x: x["next"])

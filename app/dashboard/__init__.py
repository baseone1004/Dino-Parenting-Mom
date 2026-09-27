"""관리 대시보드 (Flask)."""
from __future__ import annotations

import json
import threading

from flask import Flask, Response, redirect, render_template, request, send_from_directory, url_for, flash

from app import service, store, scheduler, trend, threads_api, facebook_api, config
from app.config import cfg, enabled_accounts
from app.slides_cards import CARDS_DIR

app = Flask(__name__, template_folder="templates")
app.secret_key = "threads-auto-local-dashboard"


@app.before_request
def _basic_auth():
    """config.yaml 의 dashboard.password 가 설정돼 있으면 모든 요청에 로그인 요구 (아이디 admin)."""
    pw = (cfg["dashboard"].get("password") or "").strip()
    if not pw:
        return None
    auth = request.authorization
    if auth and auth.type == "basic" and auth.username == "admin" and auth.password == pw:
        return None
    return Response("로그인이 필요합니다.", 401, {"WWW-Authenticate": 'Basic realm="Threads Auto"'})


def _accounts_view() -> list[dict]:
    from app.generator import load_topics
    st = store.stats()
    runs = scheduler.next_runs()
    out = []
    for a in cfg["accounts"]:
        topics = load_topics(a["id"])
        with_link = sum(1 for t in topics if t.get("link") or (t.get("product") and cfg["coupang"].get("use_api")))
        nxt = [r["next"] for r in runs if r["id"].startswith(f"slot-{a['id']}-")]
        acc_row = store.get_account(a["id"]) or {}
        pending_raw = store.get_setting(f"fb_pages_{a['id']}")
        out.append({
            **a,
            "token": service.token_status(a["id"]),
            "counts": st["by_account"].get(a["id"], {s: 0 for s in store.STATUS_LABEL}),
            "today": store.published_today(a["id"]),
            "link_allowed": service.link_allowed(a["id"]),
            "topics_total": len(topics),
            "topics_with_link": with_link,
            "topic_idx": store.get_cursor(a["id"]) % len(topics) if topics else 0,
            "next_run": min(nxt) if nxt else "-",
            "views": sum(p.get("views") or 0 for p in store.list_posts(a["id"], store.PUBLISHED, limit=500)),
            "slots_to_monday": len(service.upcoming_slots(a["id"], until=service.next_monday_end())),
            "batch": store.get_setting(f"batch_{a['id']}") or "",
            "facebook_page_id": acc_row.get("facebook_page_id"),
            "facebook_page_name": acc_row.get("facebook_page_name"),
            "instagram_business_id": acc_row.get("instagram_business_id"),
            "fb_pending_pages": json.loads(pending_raw) if pending_raw else None,
        })
    return out


@app.route("/")
def index():
    status = request.args.get("status") or None
    account = request.args.get("account") or None
    order = request.args.get("order") or "recent"
    return render_template(
        "index.html",
        mode=service.posting_mode(),
        stats=store.stats(),
        labels=store.STATUS_LABEL,
        accounts=_accounts_view(),
        posts=store.list_posts(account, status, limit=80, order=order),
        order=order,
        ideas=store.list_ideas(account, "pending"),
        logs=store.recent_logs(40),
        eta={pid: t for a in cfg["accounts"] for pid, t in service.scheduled_with_eta(a["id"]).items()},
        monday=service.next_monday_end().strftime("%m/%d"),
        jobs=scheduler.next_runs(),
        cfg=cfg,
        filter_status=status,
        filter_account=account,
    )


@app.post("/mode")
def set_mode():
    mode = request.form.get("mode", "test")
    service.set_posting_mode(mode)
    flash(f"게시 모드: {'실전 (실제 게시)' if mode == 'live' else '테스트 (초안만 저장)'}")
    return redirect(url_for("index"))


@app.post("/generate/<account_id>")
def generate(account_id):
    def work():
        try:
            service.create_post(account_id, publish=False)
        except Exception as e:
            store.log("ERROR", f"수동 생성 실패: {e}", account_id)
    threading.Thread(target=work, daemon=True).start()
    flash("초안 생성을 시작했습니다. 30초~2분 뒤 새로고침하세요.")
    return redirect(url_for("index"))


@app.post("/generate/<account_id>/batch")
def generate_batch(account_id):
    n = max(1, min(60, int(request.form.get("n", 1) or 1)))
    schedule = request.form.get("schedule") == "1"
    threading.Thread(target=service.batch_generate, args=[account_id, n, schedule], daemon=True).start()
    flash(f"{n}개 생성 시작 (1개당 1~2분). 진행 상황은 계정 카드에 표시됩니다.")
    return redirect(url_for("index"))


@app.post("/posts/schedule_all/<account_id>")
def schedule_all(account_id):
    n = 0
    for p in store.list_posts(account_id, store.DRAFT, limit=500):
        store.update_post(p["id"], status=store.SCHEDULED, error=None)
        n += 1
    flash(f"초안 {n}개를 예약 대기로 전환. 스케줄 시각마다 오래된 순서대로 게시됩니다 (실전 모드일 때).")
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/publish")
def publish(post_id):
    ok = service.publish_post(post_id)
    flash("게시 완료" if ok else "게시 실패 — 로그를 확인하세요")
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/schedule")
def schedule(post_id):
    store.update_post(post_id, status=store.SCHEDULED, error=None)
    flash("다음 스케줄 시각에 게시됩니다 (실전 모드일 때)")
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/draft")
def to_draft(post_id):
    store.update_post(post_id, status=store.DRAFT, error=None)
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/edit")
def edit(post_id):
    body = request.form.get("body", "").strip()
    link = request.form.get("link", "").strip() or None
    if body:
        store.update_post(post_id, body=body, link=link)
        flash("수정 저장")
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/delete")
def delete(post_id):
    store.delete_post(post_id)
    return redirect(url_for("index"))


@app.post("/accounts/<account_id>/token")
def set_token(account_id):
    token = request.form.get("token", "").strip()
    kind = request.form.get("kind", "long")
    if not token:
        flash("토큰을 입력하세요")
        return redirect(url_for("index"))
    try:
        if kind == "short":
            token, exp = threads_api.exchange_long_lived(token)
            me = service.save_token(account_id, token, exp)
        else:
            me = service.save_token(account_id, token)
        flash(f"@{me.get('username')} 토큰 저장 완료")
    except threads_api.ThreadsError as e:
        flash(f"토큰 오류: {e}")
    return redirect(url_for("index"))


@app.post("/accounts/<account_id>/refresh")
def refresh(account_id):
    flash("토큰 갱신 완료" if service.refresh_token(account_id) else "토큰 갱신 실패 (발급 24시간 이후, 만료 전에만 가능)")
    return redirect(url_for("index"))


@app.post("/accounts/<account_id>/facebook/fetch")
def facebook_fetch(account_id):
    user_token = request.form.get("user_token", "").strip()
    if not user_token:
        flash("페이스북 사용자 토큰을 입력하세요")
        return redirect(url_for("index"))
    try:
        pages = facebook_api.list_pages(user_token)
        if not pages:
            flash("이 토큰으로 관리 중인 페이지가 없습니다 (권한 확인 필요)")
        else:
            store.set_setting(f"fb_pages_{account_id}", json.dumps(pages))
            flash(f"페이지 {len(pages)}개 조회됨 — 연결할 페이지를 선택하세요")
    except facebook_api.FacebookError as e:
        flash(f"페이스북 토큰 오류: {e}")
    return redirect(url_for("index"))


@app.post("/accounts/<account_id>/facebook/connect")
def facebook_connect(account_id):
    page_id = request.form.get("page_id", "")
    pending_raw = store.get_setting(f"fb_pages_{account_id}")
    pages = json.loads(pending_raw) if pending_raw else []
    page = next((p for p in pages if p.get("id") == page_id), None)
    if not page:
        flash("선택한 페이지를 찾을 수 없습니다. 다시 조회하세요")
        return redirect(url_for("index"))
    ig = (page.get("instagram_business_account") or {}).get("id")
    service.save_facebook_page(account_id, page["id"], page["access_token"], page.get("name"), ig)
    store.set_setting(f"fb_pages_{account_id}", "")
    flash(f"페이스북 페이지 '{page.get('name')}' 연결 완료" + (" (인스타그램도 연결됨)" if ig else " (연결된 인스타그램 계정 없음)"))
    return redirect(url_for("index"))


@app.post("/posts/<int:post_id>/retry/<platform>")
def retry_platform(post_id, platform):
    ok = service.retry_platform(post_id, platform)
    flash(f"{platform} 재게시 {'완료' if ok else '실패 — 로그를 확인하세요'}")
    return redirect(url_for("index"))


@app.route("/media/cards/<int:post_id>/<path:filename>")
def media_cards(post_id, filename):
    return send_from_directory(CARDS_DIR / str(post_id), filename)


@app.post("/ideas/collect/<account_id>")
def collect_ideas(account_id):
    threading.Thread(target=trend.collect, args=[account_id], daemon=True).start()
    flash("글감 수집 시작. 1~2분 뒤 새로고침하세요.")
    return redirect(url_for("index"))


@app.post("/ideas/<int:idea_id>/<action>")
def idea_action(idea_id, action):
    store.set_idea_status(idea_id, "approved" if action == "approve" else "rejected")
    return redirect(url_for("index"))


@app.post("/insights")
def insights():
    threading.Thread(target=service.refresh_insights, daemon=True).start()
    flash("성과 수집 시작. 잠시 후 새로고침하세요.")
    return redirect(url_for("index"))


@app.post("/reload")
def reload_config():
    config.reload()
    flash("config.yaml 다시 읽음 (스케줄 시각 변경은 프로그램 재시작 필요)")
    return redirect(url_for("index"))


def run():
    d = cfg["dashboard"]
    app.run(host=d.get("host", "127.0.0.1"), port=int(d.get("port", 5000)), debug=False, use_reloader=False)

"""스케줄러와 대시보드가 공유하는 핵심 동작: 글 생성/저장, 게시, 링크, 토큰."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta

from app import store, coupang, toss, threads_api, facebook_api, instagram_api, slides_cards, telegram_notify
from app import product_image, kie_image
from app.config import cfg, account_cfg, env
from app.generator import generate_post, build_card_slides, pick_topic

log = logging.getLogger("service")


# ---------------- 모드 ----------------
def posting_mode() -> str:
    return store.get_setting("posting_mode") or cfg["posting"].get("mode", "test")


def set_posting_mode(mode: str):
    assert mode in ("test", "live")
    store.set_setting("posting_mode", mode)
    store.log("INFO", f"게시 모드 변경 → {mode}")


# ---------------- 토큰 ----------------
def account_token(account_id: str) -> tuple[str | None, str | None]:
    """(token, threads_user_id). DB 우선, 없으면 .env THREADS_TOKEN_<ID>."""
    row = store.get_account(account_id) or {}
    token = row.get("access_token") or env(f"THREADS_TOKEN_{account_id.upper()}") or None
    return token, row.get("threads_user_id")


def facebook_credentials(account_id: str) -> tuple[str | None, str | None]:
    """(page_id, page_token)."""
    row = store.get_account(account_id) or {}
    return row.get("facebook_page_id"), row.get("facebook_page_token")


def instagram_credentials(account_id: str) -> tuple[str | None, str | None]:
    """(ig_business_id, page_token) — 인스타그램은 연결된 페이지의 토큰을 그대로 사용."""
    row = store.get_account(account_id) or {}
    return row.get("instagram_business_id"), row.get("facebook_page_token")


def save_facebook_page(account_id: str, page_id: str, page_token: str, page_name: str | None,
                       ig_business_id: str | None):
    store.upsert_account(account_id, facebook_page_id=page_id, facebook_page_token=page_token,
                         facebook_page_name=page_name, instagram_business_id=ig_business_id)
    store.log("INFO", f"페이스북 페이지 연결 완료 ({page_name or page_id})"
                      + (f" · 인스타그램 연결됨" if ig_business_id else " · 인스타그램 미연결"), account_id)


def save_token(account_id: str, token: str, expires_at: datetime | None = None) -> dict:
    """토큰 검증(get_me) 후 저장. 만료일 미지정 시 60일."""
    me = threads_api.get_me(token)
    exp = expires_at or (datetime.now() + timedelta(days=60))
    store.upsert_account(account_id, threads_user_id=me["id"], username=me.get("username"),
                         access_token=token, token_expires_at=exp.strftime("%Y-%m-%d %H:%M:%S"))
    store.log("INFO", f"토큰 저장 (@{me.get('username')}, 만료 {exp:%Y-%m-%d})", account_id)
    return me


def token_status(account_id: str) -> dict:
    """대시보드용: {'has': bool, 'expires_at': str|None, 'days_left': int|None, 'warn': bool}"""
    row = store.get_account(account_id) or {}
    token, _ = account_token(account_id)
    exp = row.get("token_expires_at")
    days = None
    if exp:
        days = (datetime.strptime(exp, "%Y-%m-%d %H:%M:%S") - datetime.now()).days
    warn_days = int(cfg.get("token_warn_days", 7))
    return {"has": bool(token), "username": row.get("username"), "expires_at": exp,
            "days_left": days, "warn": (days is not None and days <= warn_days) or not token}


def refresh_token(account_id: str) -> bool:
    token, _ = account_token(account_id)
    if not token:
        return False
    try:
        new_token, exp = threads_api.refresh_long_lived(token)
        save_token(account_id, new_token, exp)
        return True
    except threads_api.ThreadsError as e:
        store.log("ERROR", f"토큰 갱신 실패: {e}", account_id)
        return False


def refresh_expiring_tokens():
    """매일 실행: 만료 임박 토큰 자동 갱신."""
    for acc in cfg["accounts"]:
        st = token_status(acc["id"])
        if st["has"] and st["days_left"] is not None and st["days_left"] <= int(cfg.get("token_warn_days", 7)):
            refresh_token(acc["id"])


# ---------------- 성과 측정 ----------------
def refresh_insights(days: int = 30):
    """최근 게시글의 조회수/좋아요/댓글을 가져와 저장 (학습 루프의 입력)."""
    for acc in cfg["accounts"]:
        token, _ = account_token(acc["id"])
        if not token:
            continue
        n = 0
        for p in store.published_recent(acc["id"], days):
            try:
                ins = threads_api.get_insights(p["threads_post_id"], token)
            except threads_api.ThreadsError as e:
                store.log("WARN", f"#{p['id']} 성과 조회 실패: {e}", acc["id"])
                continue
            store.update_post(p["id"], views=ins.get("views", 0), likes=ins.get("likes", 0),
                              replies=ins.get("replies", 0), reposts=ins.get("reposts", 0), insights_at=store.now())
            n += 1
        if n:
            store.log("INFO", f"성과 갱신 {n}건", acc["id"])


# ---------------- 링크 ----------------
def link_allowed(account_id: str) -> bool:
    if not cfg["coupang"].get("enabled", True) or cfg["posting"].get("link_placement", "body") == "none":
        return False
    acc = account_cfg(account_id) or {}
    started = acc.get("started_at")
    after = int(acc.get("link_after_days", 0) or 0)
    if started and after:
        try:
            started_d = datetime.strptime(str(started), "%Y-%m-%d").date()
            if (date.today() - started_d).days < after:
                return False
        except ValueError:
            pass
    return True


def build_link_line(account_id: str, topic: dict) -> str | None:
    if not link_allowed(account_id):
        return None
    url = topic.get("link")
    if not url and topic.get("product") and cfg["coupang"].get("use_api", False):
        try:
            url = coupang.link_for_keyword(topic["product"])
        except Exception as e:  # 키 없음/네트워크 오류여도 글은 링크 없이 저장
            store.log("WARN", f"쿠팡 링크 생성 실패 ({topic['product']}): {e}", account_id)
            url = None
    if not url:
        return None
    prefix = cfg["coupang"].get("link_prefix", "")
    line = f"{prefix}{url}"
    disc = cfg["coupang"].get("disclosure")
    if disc:
        line += f"\n{disc}"
    return line


# ---------------- 예약 슬롯 ----------------
def upcoming_slots(account_id: str, until: datetime | None = None, limit: int = 60) -> list[datetime]:
    """지금 이후의 게시 슬롯 시각 목록 (오늘 이미 게시한 수는 제외)."""
    times = sorted(cfg["posting"].get("times") or ["09:00", "14:00", "20:00"])
    limit_per_day = int(cfg["posting"].get("max_per_day", 3))
    now = datetime.now()
    out, day = [], now.date()
    used_today = store.published_today(account_id)
    for d in range(0, 30):
        cur = day + timedelta(days=d)
        n = used_today if d == 0 else 0
        for t in times:
            hh, mm = map(int, t.split(":"))
            slot = datetime(cur.year, cur.month, cur.day, hh, mm)
            if slot <= now or n >= limit_per_day:
                continue
            if until and slot > until:
                return out
            out.append(slot)
            n += 1
            if len(out) >= limit:
                return out
    return out


def next_monday_end() -> datetime:
    now = datetime.now()
    days = (7 - now.weekday()) % 7 or 7          # 다음 월요일 (오늘이 월요일이면 다음 주)
    if now.weekday() == 0:
        days = 0                                  # 오늘이 월요일이면 오늘까지
    d = (now + timedelta(days=days)).date()
    return datetime(d.year, d.month, d.day, 23, 59)


def scheduled_with_eta(account_id: str) -> dict[int, str]:
    """예약 대기 글 id → 예정 시각 문자열."""
    pend = store.list_posts(account_id, store.SCHEDULED, limit=200)
    pend.sort(key=lambda p: p["id"])
    slots = upcoming_slots(account_id, limit=len(pend))
    return {p["id"]: (slots[i].strftime("%m/%d %H:%M") if i < len(slots) else "-") for i, p in enumerate(pend)}


def batch_generate(account_id: str, n: int, schedule: bool = False):
    """초안 n개를 순서대로 생성 (백그라운드용). schedule=True 면 바로 예약 대기로."""
    store.set_setting(f"batch_{account_id}", f"0/{n}")
    for i in range(n):
        try:
            post = create_post(account_id, publish=False)
            if schedule:
                store.update_post(post["id"], status=store.SCHEDULED)
        except Exception as e:
            store.log("ERROR", f"일괄 생성 {i+1}/{n} 실패: {e}", account_id)
        store.set_setting(f"batch_{account_id}", f"{i+1}/{n}")
    store.set_setting(f"batch_{account_id}", "")
    store.log("INFO", f"일괄 생성 완료 ({n}개)", account_id)


# ---------------- 생성 → 저장/게시 ----------------
def resolve_auto_product(account_id: str, topic: dict):
    """topic['product'] 가 'AUTO' 면 트렌드 상품을 실제로 뽑아 product/link 를 채움 (실패하면 product 없이 진행)."""
    if topic.get("product") != "AUTO":
        return
    acc = account_cfg(account_id) or {}
    source = acc.get("link_source", "coupang")
    try:
        if source == "toss" and cfg["toss"].get("use_api", False):
            item = toss.pick_trending_product()
            topic["product"] = item.get("displayName")
            topic["link"] = toss.link_for_item(item["tacaItemId"])
        else:
            topic["product"] = None
    except Exception as e:
        store.log("WARN", f"자동 상품 선정 실패, 상품 없이 진행: {e}", account_id)
        topic["product"] = None


def create_post(account_id: str, publish: bool | None = None, topic: dict | None = None) -> dict:
    """글 1개 생성. publish=None 이면 현재 모드에 따름(test→초안, live→즉시 게시)."""
    if publish is None:
        publish = posting_mode() == "live"
    topic = topic or pick_topic(account_id)
    resolve_auto_product(account_id, topic)
    topic, body = generate_post(account_id, topic)
    link = build_link_line(account_id, topic)
    post_id = store.add_post(account_id, topic.get("title", ""), body, link, store.DRAFT,
                             product_url=topic.get("link"))
    store.log("INFO", f"글 생성 #{post_id} · {topic.get('title','')[:40]}", account_id)
    if publish:
        publish_post(post_id)
    return store.get_post(post_id)


def public_base_url() -> str:
    return (cfg["dashboard"].get("public_base_url") or "").rstrip("/")


def publish_facebook(post_id: int) -> bool:
    """페이스북 페이지에 게시 (실패해도 다른 플랫폼에 영향 없음)."""
    post = store.get_post(post_id)
    if not post or not cfg["facebook"].get("enabled", True):
        return False
    account_id = post["account_id"]
    page_id, page_token = facebook_credentials(account_id)
    if not page_id or not page_token:
        store.update_post(post_id, facebook_error="페이스북 페이지 미연결 (대시보드에서 연결)")
        return False
    try:
        image_urls = ensure_card_images(post)
        if image_urls:
            fid = facebook_api.publish_multi_photo_with_link(page_id, page_token, post["body"], image_urls, post["link"])
        else:
            fid = facebook_api.publish_with_link(page_id, page_token, post["body"], post["link"])
        store.update_post(post_id, facebook_post_id=fid, facebook_error=None)
        store.log("INFO", f"#{post_id} 페이스북 게시 완료 (id {fid})", account_id)
        return True
    except Exception as e:
        store.update_post(post_id, facebook_error=str(e)[:500])
        store.log("ERROR", f"#{post_id} 페이스북 게시 실패: {e}", account_id)
        return False


def cover_image_for(post: dict) -> str | None:
    """상품 링크가 있으면 그 상품 이미지, 없으면 KIE.AI 로 글 내용에 맞는 이미지를 생성 (실패하면 None — 이미지 없이 진행)."""
    account_id = post["account_id"]
    if post.get("product_url"):
        img = product_image.fetch_og_image(post["product_url"])
        if img:
            return img
        store.log("WARN", f"#{post['id']} 상품 이미지 추출 실패, AI 이미지로 대체", account_id)
    try:
        # 본문을 그대로 넣으면 모델이 "이 문장을 이미지에 그려야 한다"고 오해해 깨진 가짜 텍스트를 그리는 경우가
        # 있어 주제 한 줄만 분위기 힌트로 쓰고, 텍스트/화면/글자 금지를 영어로 강하게 명시.
        prompt = (
            "A single high-quality lifestyle photograph, warm and cozy editorial style, soft natural lighting, "
            "no people's faces close-up needed. Absolutely no text, no letters, no words, no captions, "
            "no screenshots, no phone or app UI, no logos, no watermarks anywhere in the image — a completely "
            f"clean photographic scene only. Mood/topic to reflect: {post.get('topic', '')}"
        )
        return kie_image.generate_image(prompt)
    except Exception as e:
        store.log("WARN", f"#{post['id']} KIE 이미지 생성 실패: {e}", account_id)
        return None


def ensure_card_images(post: dict) -> list[str] | None:
    """이 글의 카드뉴스 이미지 URL 목록을 구해서 반환 (없으면 생성해 DB 에 캐싱).
    페이스북·인스타그램이 같은 이미지 세트를 공유 — 먼저 요청한 쪽이 생성하고 다음 쪽은 캐시를 씀.
    public_base_url 미설정이면 None."""
    image_urls = json.loads(post["card_image_urls"]) if post.get("card_image_urls") else None
    if image_urls:
        return image_urls
    base = public_base_url()
    if not base:
        return None
    try:
        slide_texts = build_card_slides({"title": post.get("topic", "")}, post["body"])
        cover_image_url = cover_image_for(post)
        paths = slides_cards.render_cards(post["id"], post.get("topic") or "", slide_texts, cover_image_url)
    except Exception as e:
        # 카드뉴스 생성 실패는 페이스북(텍스트만으로 대체 가능)까지 막으면 안 됨 — 여기서 삼키고 None 반환.
        store.log("WARN", f"#{post['id']} 카드뉴스 이미지 생성 실패 (텍스트만 게시로 대체): {e}", post["account_id"])
        return None
    image_urls = [f"{base}/media/cards/{post['id']}/{p.name}" for p in paths]
    store.update_post(post["id"], card_image_urls=json.dumps(image_urls))
    return image_urls


def publish_instagram(post_id: int) -> bool:
    """인스타그램에 카드뉴스 캐러셀로 게시 (실패해도 다른 플랫폼에 영향 없음)."""
    post = store.get_post(post_id)
    if not post or not cfg["instagram"].get("enabled", True):
        return False
    account_id = post["account_id"]
    ig_id, page_token = instagram_credentials(account_id)
    if not ig_id or not page_token:
        store.update_post(post_id, instagram_error="인스타그램 미연결 (대시보드에서 페이스북 페이지 연결 필요)")
        return False
    try:
        image_urls = ensure_card_images(post)
        if not image_urls:
            reason = "dashboard.public_base_url 미설정" if not public_base_url() else "카드뉴스 이미지 생성 실패 (로그 확인)"
            store.update_post(post_id, instagram_error=reason)
            return False
        mid = instagram_api.publish_carousel_with_link(ig_id, page_token, image_urls, post["body"], post["link"])
        store.update_post(post_id, instagram_post_id=mid, instagram_error=None)
        store.log("INFO", f"#{post_id} 인스타그램 게시 완료 (id {mid})", account_id)
        return True
    except Exception as e:
        store.update_post(post_id, instagram_error=str(e)[:500])
        store.log("ERROR", f"#{post_id} 인스타그램 게시 실패: {e}", account_id)
        return False


def publish_post(post_id: int) -> bool:
    """Threads 게시(기존 로직) 후, 페이스북/인스타그램도 각각 독립적으로 시도.
    반환값은 Threads 기준(스케줄링/한도 로직이 Threads 를 기준으로 하므로)."""
    post = store.get_post(post_id)
    if not post:
        return False
    account_id = post["account_id"]
    token, user_id = account_token(account_id)
    if not token:
        store.update_post(post_id, status=store.FAILED, error="Threads 토큰 없음 (대시보드 > 설정에서 입력)")
        store.log("ERROR", f"#{post_id} 게시 실패: 토큰 없음", account_id)
        return False
    if not user_id:
        try:
            user_id = save_token(account_id, token)["id"]
        except threads_api.ThreadsError as e:
            store.update_post(post_id, status=store.FAILED, error=f"토큰 검증 실패: {e}")
            return False

    limit = int(cfg["posting"].get("max_per_day", 3))
    if store.published_today(account_id) >= limit:
        store.update_post(post_id, status=store.SCHEDULED, error=f"오늘 게시 한도({limit}) 도달 → 예약 대기로 전환")
        store.log("WARN", f"#{post_id} 오늘 한도 도달, 예약 대기", account_id)
        return False

    placement = cfg["posting"].get("link_placement", "body")
    retries = int(cfg["posting"].get("retry", 3))
    last_err = ""
    threads_ok = False
    for attempt in range(1, retries + 1):
        try:
            tid = threads_api.publish_with_link(user_id, token, post["body"], post["link"], placement)
            store.update_post(post_id, status=store.PUBLISHED, threads_post_id=tid, error=None,
                              attempts=attempt, published_at=store.now())
            store.log("INFO", f"#{post_id} 게시 완료 (threads id {tid})", account_id)
            threads_ok = True
            break
        except threads_api.ThreadsError as e:
            last_err = str(e)
            store.log("WARN", f"#{post_id} 게시 시도 {attempt}/{retries} 실패: {last_err[:200]}", account_id)
            time.sleep(10 * attempt)
    if not threads_ok:
        store.update_post(post_id, status=store.FAILED, error=last_err[:500], attempts=retries)
        store.log("ERROR", f"#{post_id} 게시 최종 실패", account_id)

    fb_ok = publish_facebook(post_id)
    ig_ok = publish_instagram(post_id)

    acc_name = (account_cfg(account_id) or {}).get("name", account_id)
    mark = lambda ok: "✅" if ok else "❌"
    title = post.get("topic", "")[:40]
    telegram_notify.send(
        f"{mark(threads_ok)} {acc_name} 게시 결과\n"
        f"제목: {title}\n"
        f"Threads {mark(threads_ok)} · Facebook {mark(fb_ok)} · Instagram {mark(ig_ok)}"
    )
    return threads_ok


def retry_platform(post_id: int, platform: str) -> bool:
    """실패한 플랫폼 하나만 재시도 (대시보드용)."""
    if platform == "facebook":
        return publish_facebook(post_id)
    if platform == "instagram":
        return publish_instagram(post_id)
    if platform == "threads":
        return publish_post(post_id)
    return False


def run_slot(account_id: str):
    """스케줄 시각에 호출. 예약 대기 글이 있으면 그것을 먼저 게시, 없으면 새로 생성."""
    acc = account_cfg(account_id)
    if not acc or not acc.get("enabled", True):
        return
    mode = posting_mode()
    try:
        if mode == "live":
            pending = store.next_scheduled(account_id)
            if pending:
                publish_post(pending["id"])
                return
        create_post(account_id, publish=(mode == "live"))
    except Exception as e:  # 스케줄러가 죽지 않도록 전부 잡는다
        log.exception("run_slot 실패")
        store.log("ERROR", f"슬롯 실행 실패: {e}", account_id)

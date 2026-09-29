"""스케줄러와 대시보드가 공유하는 핵심 동작: 글 생성/저장, 게시, 링크, 토큰."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from app import store, coupang, toss, threads_api, facebook_api, instagram_api, slides_cards, telegram_notify
from app import product_image, kie_image
from app.config import cfg, account_cfg, env
from app.generator import generate_post, build_card_slides, pick_topic, to_formal_body

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
    is_toss = (account_cfg(account_id) or {}).get("link_source") == "toss"
    src_cfg = cfg["toss"] if is_toss else cfg["coupang"]
    prefix = src_cfg.get("link_prefix", "")
    line = f"{prefix}{url}"
    disc = src_cfg.get("disclosure")
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
def _daily_product_key(account_id: str) -> str:
    return f"daily_product_{account_id}_{date.today():%Y%m%d}"


def select_daily_product(account_id: str, force: bool = False) -> dict | None:
    """계정별 인기 상품을 하루 한 번만 조회해 API 호출 제한을 보호한다."""
    acc = account_cfg(account_id) or {}
    if not acc.get("auto_product", False):
        return None
    key = _daily_product_key(account_id)
    if not force:
        cached = store.get_setting(key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass
    source = acc.get("link_source", "coupang")
    try:
        if source == "toss" and cfg["toss"].get("use_api", False):
            item = toss.pick_trending_product()
            result = {
                "product": item.get("displayName"),
                "link": toss.link_for_item(item["tacaItemId"]),
                "product_id": item.get("tacaItemId"),
                "source": "toss",
            }
        elif source == "coupang" and cfg["coupang"].get("use_api", False) \
                and env("COUPANG_ACCESS_KEY") and env("COUPANG_SECRET_KEY"):
            item = coupang.pick_product_for_keywords(acc.get("product_keywords") or [])
            result = {
                "product": item.get("productName"),
                "link": item.get("productUrl"),
                "product_id": item.get("productId"),
                "source": "coupang",
            }
        else:
            return None
        if not result.get("product") or not result.get("link"):
            raise RuntimeError(f"상품명 또는 링크가 없는 응답: {result}")
        store.set_setting(key, json.dumps(result, ensure_ascii=False))
        store.log("INFO", f"오늘의 인기 상품 선정 ({source}): {result['product'][:60]}", account_id)
        return result
    except Exception as e:
        store.log("WARN", f"오늘의 인기 상품 선정 실패, 기존 주제 상품 사용: {e}", account_id)
        return None


def refresh_daily_products():
    """매일 아침 실행되는 인기 상품 준비 작업."""
    for acc in cfg["accounts"]:
        if acc.get("enabled", True) and acc.get("auto_product", False):
            select_daily_product(acc["id"])


def resolve_auto_product(account_id: str, topic: dict):
    """자동상품 계정은 오늘의 인기 상품을 주제에 주입한다. API 미설정/실패 시 기존 값을 보존한다."""
    acc = account_cfg(account_id) or {}
    if topic.get("product") != "AUTO" and not acc.get("auto_product", False):
        return
    item = select_daily_product(account_id)
    if item:
        topic["product"] = item["product"]
        topic["link"] = item["link"]


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
    if post.get("facebook_post_id"):
        return True
    account_id = post["account_id"]
    page_id, page_token = facebook_credentials(account_id)
    if not page_id or not page_token:
        store.update_post(post_id, facebook_error="페이스북 페이지 미연결 (대시보드에서 연결)")
        return False
    try:
        body = ensure_formal_body(post)
        image_urls = ensure_card_images(post)
        if image_urls:
            fid = facebook_api.publish_multi_photo_with_link(page_id, page_token, body, image_urls, post["link"])
        else:
            fid = facebook_api.publish_with_link(page_id, page_token, body, post["link"])
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


CARD_STYLE_BASE = (
    "clean flat 2D illustration style (not photorealistic, not a 3D render), warm pastel color "
    "palette (ivory, cream, light beige, soft pink, soft sky blue, soft mint, soft orange), only "
    "1-2 accent colors, generous white space, minimal small decorative icons (stars, hearts, dots, "
    "small flower, small shopping bag, small box, small kitchen or home icon) that never outshine "
    "the title or product, friendly warm trustworthy everyday-life SNS content look, not an obvious "
    "advertisement"
)


def _card_style_hint(account_id: str) -> str:
    return (account_cfg(account_id) or {}).get("card_style") or CARD_STYLE_BASE


def _card_prompt(title: str, style_hint: str, eyebrow: str, edit_mode: bool) -> str:
    """AI 에게는 제목(짧은 텍스트)과 일러스트만 맡긴다 — 부제목/체크리스트/CTA 같은 긴 문장은
    gpt-image-1 이 종종 오타를 내서, 생성 후 compose_text_panel 로 정확한 폰트를 직접 덧그린다."""
    eyebrow_line = f'A small eyebrow label near the very top, exactly: "{eyebrow}"\n' if eyebrow else ""
    intro = ("Edit this product photo into a single Korean-language SNS card-news image for "
            "Instagram and Facebook feed, vertical portrait format. Keep the product in the photo "
            "exactly as shown, unchanged and clearly visible, with generous empty space around it "
            "for the added design elements."
            if edit_mode else
            "Create a single Korean-language SNS card-news image for Instagram and Facebook feed.")
    return f"""{intro}
Style: {style_hint}
Vertical portrait card, mobile-optimized, high resolution, sharp accurately-rendered Korean text.
Generous safe margins on all sides (top/bottom/left/right) — never place text at the very edge.
Layout, top to bottom:
{eyebrow_line}A large bold Korean headline (wrap into 1-2 short lines naturally), exactly: "{title}" —
make it the strongest visual element, emphasize 1-3 key words with an accent color or soft badge.
{"Below the headline, keep the product photo large and centered, clearly recognizable." if edit_mode else
 "Below the headline, a large centered illustration of the main everyday product or scene related "
 "to the topic, clearly recognizable, with enough empty space around it."}
Leave the bottom about 40% of the image as clean, mostly plain background in the same pastel color
scheme, with no text and no busy decoration there — separate text will be added there afterward.
Do not add any other text, watermarks, fake brand logos, fake star ratings, fake review counts, fake
discount percentages, or exaggerated "무조건 사세요"-style language.
"""


def render_cards_openai(post: dict, slide_texts: list[str]) -> list[Path]:
    """OpenAI gpt-image-1 로 카드뉴스를 1장짜리 완결형 이미지로 생성. 제목+일러스트만 AI 가 그리고,
    부제목·체크리스트·CTA 는 정확한 폰트로 직접 덧그림 (긴 문장에서 AI 오타 방지).
    실제 상품 사진이 있으면 그 사진을 기반으로 편집(상품 실물 유지)."""
    from app import openai_image
    account_id = post["account_id"]
    style_hint = _card_style_hint(account_id)
    title = post.get("topic") or ""
    subtitle = slide_texts[0] if slide_texts else ""
    points = list(slide_texts[1:4])
    out_dir = slides_cards.CARDS_DIR / str(post["id"])
    out_dir.mkdir(parents=True, exist_ok=True)

    is_toss = (account_cfg(account_id) or {}).get("link_source") == "toss"
    has_link = bool(post.get("link"))
    eyebrow = ("오늘 발견한 생활템" if is_toss else "요즘 잘 나가는 생활템") if has_link else ""
    # 이모지는 PIL 로 그릴 때 NanumGothic 에 없어서 빈 네모로 깨짐 — 텍스트만 사용.
    cta = "자세한 정보는 프로필 링크에서 확인" if has_link else "저장해두고 나중에 확인하세요"

    product_bytes = None
    if post.get("product_url"):
        img_url = product_image.fetch_og_image(post["product_url"])
        if img_url:
            try:
                product_bytes = openai_image.fetch_bytes(img_url)
            except Exception as e:
                store.log("WARN", f"#{post['id']} 상품 이미지 다운로드 실패: {e}", account_id)

    prompt = _card_prompt(title, style_hint, eyebrow, edit_mode=bool(product_bytes))
    img_bytes = openai_image.edit_image(product_bytes, prompt) if product_bytes else openai_image.generate_image(prompt)
    img_bytes = openai_image.compose_text_panel(img_bytes, subtitle, points, cta)
    p = out_dir / "1.png"
    p.write_bytes(img_bytes)
    return [p]


def ensure_card_images(post: dict) -> list[str] | None:
    """이 글의 카드뉴스 이미지 URL 목록을 구해서 반환 (없으면 생성해 DB 에 캐싱).
    페이스북·인스타그램이 같은 이미지 세트를 공유 — 먼저 요청한 쪽이 생성하고 다음 쪽은 캐시를 씀.
    public_base_url 미설정이면 None. OPENAI_API_KEY 가 있으면 gpt-image-1 로 문구까지 그려 넣고,
    없으면 기존 구글 슬라이드(사진+텍스트 오버레이) 방식으로 대체."""
    image_urls = json.loads(post["card_image_urls"]) if post.get("card_image_urls") else None
    if image_urls:
        return image_urls
    base = public_base_url()
    if not base:
        return None
    try:
        slide_texts = build_card_slides({"title": post.get("topic", "")}, ensure_formal_body(post))
        paths = None
        if env("OPENAI_API_KEY"):
            try:
                paths = render_cards_openai(post, slide_texts)
            except Exception:
                log.exception("OpenAI 카드 생성 실패, Google Slides/로컬 카드로 대체")
                store.log("WARN", f"#{post['id']} OpenAI 카드 생성 실패, 대체 렌더러 사용", post["account_id"])
        if paths is None and env("GOOGLE_OAUTH_CLIENT_ID") and env("GOOGLE_OAUTH_CLIENT_SECRET") \
                and env("GOOGLE_OAUTH_REFRESH_TOKEN") and env("SLIDES_TEMPLATE_ID"):
            try:
                cover_image_url = cover_image_for(post)
                font_family = (account_cfg(post["account_id"]) or {}).get("card_font")
                paths = slides_cards.render_cards(post["id"], post.get("topic") or "", slide_texts,
                                                  cover_image_url, font_family)
            except Exception:
                log.exception("Google Slides 카드 생성 실패, 로컬 카드로 대체")
                store.log("WARN", f"#{post['id']} Google Slides 카드 생성 실패, 로컬 렌더러 사용",
                          post["account_id"])
        if paths is None:
            from app.local_cards import render_cards as render_local_cards
            cover_image_url = cover_image_for(post)
            paths = render_local_cards(post["id"], post.get("topic") or "", slide_texts, cover_image_url,
                                       post["account_id"])
    except Exception as e:
        # 카드뉴스 생성 실패는 페이스북(텍스트만으로 대체 가능)까지 막으면 안 됨 — 여기서 삼키고 None 반환.
        log.exception("카드뉴스 이미지 생성 최종 실패")
        store.log("WARN", f"#{post['id']} 카드뉴스 이미지 생성 실패 (텍스트만 게시로 대체): {e}", post["account_id"])
        return None
    image_urls = [f"{base}/media/cards/{post['id']}/{p.name}" for p in paths]
    store.update_post(post["id"], card_image_urls=json.dumps(image_urls))
    return image_urls


def ensure_formal_body(post: dict) -> str:
    """페이스북·인스타그램용 존댓말 본문을 구해서 반환 (없으면 변환해 DB 에 캐싱, 두 플랫폼이 공유).
    변환 실패 시 원문(반말) 그대로 사용."""
    if post.get("body_formal"):
        return post["body_formal"]
    try:
        formal = to_formal_body(post["body"])
    except Exception as e:
        store.log("WARN", f"#{post['id']} 존댓말 변환 실패 (원문 그대로 게시): {e}", post["account_id"])
        return post["body"]
    store.update_post(post["id"], body_formal=formal)
    return formal


def publish_instagram(post_id: int) -> bool:
    """인스타그램에 카드뉴스 캐러셀로 게시 (실패해도 다른 플랫폼에 영향 없음)."""
    post = store.get_post(post_id)
    if not post or not cfg["instagram"].get("enabled", True):
        return False
    if post.get("instagram_post_id"):
        return True
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
        body = ensure_formal_body(post)
        mid = instagram_api.publish_carousel_with_link(ig_id, page_token, image_urls, body, post["link"])
        store.update_post(post_id, instagram_post_id=mid, instagram_error=None)
        store.log("INFO", f"#{post_id} 인스타그램 게시 완료 (id {mid})", account_id)
        return True
    except Exception as e:
        store.update_post(post_id, instagram_error=str(e)[:500])
        store.log("ERROR", f"#{post_id} 인스타그램 게시 실패: {e}", account_id)
        return False


def publish_threads(post_id: int) -> bool:
    """Threads 한 곳만 게시한다. 플랫폼별 재시도에서 다른 채널을 건드리지 않는다."""
    post = store.get_post(post_id)
    if not post:
        return False
    if post.get("threads_post_id"):
        return True
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

    return threads_ok


def publish_post(post_id: int) -> bool:
    """세 플랫폼을 각각 한 번만 시도하며, 동시 실행을 DB 상태로 차단한다."""
    original = store.get_post(post_id)
    if not original:
        return False
    if not store.claim_post(post_id):
        store.log("WARN", f"#{post_id} 이미 게시 작업 진행 중 — 중복 요청 무시", original["account_id"])
        return False
    try:
        threads_ok = publish_threads(post_id)
        fb_ok = publish_facebook(post_id)
        ig_ok = publish_instagram(post_id)

        current = store.get_post(post_id) or original
        final_status = store.PUBLISHED if current.get("threads_post_id") else store.FAILED
        store.update_post(post_id, status=final_status)

        account_id = original["account_id"]
        acc_name = (account_cfg(account_id) or {}).get("name", account_id)
        mark = lambda ok: "✅" if ok else "❌"
        title = original.get("topic", "")[:40]
        telegram_notify.send(
            f"{mark(threads_ok)} {acc_name} 게시 결과\n"
            f"제목: {title}\n"
            f"Threads {mark(threads_ok)} · Facebook {mark(fb_ok)} · Instagram {mark(ig_ok)}"
        )
        return threads_ok
    except Exception:
        log.exception("게시 오케스트레이션 실패")
        current = store.get_post(post_id) or original
        store.update_post(post_id, status=store.PUBLISHED if current.get("threads_post_id") else store.FAILED)
        return False
    finally:
        store.release_post(post_id)


def retry_platform(post_id: int, platform: str) -> bool:
    """실패한 플랫폼 하나만 재시도 (대시보드용)."""
    if platform == "facebook":
        return publish_facebook(post_id)
    if platform == "instagram":
        return publish_instagram(post_id)
    if platform == "threads":
        return publish_threads(post_id)
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

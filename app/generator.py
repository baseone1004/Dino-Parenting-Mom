"""주제 선택 + 글 생성 (규칙 파일 적용, 자가 검수)."""
from __future__ import annotations

import random
import re

import yaml

from app import store
from app.ai_backend import get_backend
from app.config import cfg, account_cfg, account_dir


# ---------------- 주제 ----------------
def load_topics(account_id: str) -> list[dict]:
    p = account_dir(account_id) / "topics.yaml"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    topics = data.get("topics") or []
    # 문자열만 적어도 되게
    return [{"title": t} if isinstance(t, str) else t for t in topics]


def pick_topic(account_id: str) -> dict:
    """승인된 글감이 있으면 먼저 사용, 없으면 topics.yaml 순환."""
    idea = store.pop_approved_idea(account_id)
    if idea:
        return {"title": idea["title"], "angle": idea.get("angle"), "product": idea.get("product"), "source": "idea"}

    topics = load_topics(account_id)
    if not topics:
        raise RuntimeError(f"accounts/{account_id}/topics.yaml 에 주제가 없습니다.")
    acc = account_cfg(account_id) or {}
    if acc.get("topic_order") == "random":
        return dict(random.choice(topics))
    idx = store.get_cursor(account_id) % len(topics)
    store.set_cursor(account_id, (idx + 1) % len(topics))
    return dict(topics[idx])


# ---------------- 프롬프트 ----------------
def _read(account_id: str, name: str) -> str:
    p = account_dir(account_id) / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def build_system(account_id: str) -> str:
    rules = _read(account_id, "rules.md")
    profile = _read(account_id, "profile.md")
    max_chars = cfg["posting"].get("max_chars", 420)
    examples = ""
    top_n = int((cfg.get("insights") or {}).get("top_examples", 3) or 0)
    if top_n:
        tops = store.top_posts(account_id, top_n)
        if tops:
            examples = "\n[이 계정에서 반응이 좋았던 글 — 첫 줄 훅과 리듬을 참고하되 내용은 베끼지 말 것]\n"
            for t in tops:
                examples += f"(조회 {t['views']}, 댓글 {t['replies']})\n{t['body']}\n---\n"
    return f"""당신은 Threads(스레드)에 올릴 짧은 글을 쓰는 작가입니다. 아래 [프로필]의 사람이 직접 쓴 것처럼 1인칭으로 씁니다.
[말투 규칙]을 문자 그대로 지키세요. 규칙을 어기면 그 글은 실패입니다.
출력은 글 본문만. 제목, 따옴표, 설명, "다음은 ~입니다" 같은 서두를 절대 붙이지 마세요.
본문은 {max_chars}자를 넘기지 마세요.

[프로필]
{profile}

[말투 규칙]
{rules}
{examples}"""


def build_user(topic: dict) -> str:
    s = f"주제: {topic.get('title')}\n"
    if topic.get("angle"):
        s += f"관점/감정: {topic['angle']}\n"
    if topic.get("product"):
        s += f"(이 글은 '{topic['product']}' 를 자연스럽게 경험담으로 한 번 언급합니다. 광고처럼 쓰지 마세요. 링크는 제가 따로 붙이니 넣지 마세요.)\n"
    s += "\n위 주제로 글 한 편을 쓰세요. 본문만 출력하세요."
    return s


def build_review(body: str, account_id: str) -> str:
    rules = _read(account_id, "rules.md")
    max_chars = cfg["posting"].get("max_chars", 420)
    return f"""아래 [초안]을 [말투 규칙]의 '자가 검수 체크리스트'와 '절대 금지' 항목 기준으로 검사하고, 어긴 부분을 고친 최종본만 출력하세요.
문제가 없으면 초안을 그대로 출력하세요. 설명이나 체크 결과는 쓰지 말고 본문만 출력하세요. {max_chars}자 이내.

[말투 규칙]
{rules}

[초안]
{body}
"""


def clean(text: str) -> str:
    t = text.strip()
    # 코드펜스/따옴표/마크다운 잔여물 제거
    t = re.sub(r"^```[a-z]*\n?|\n?```$", "", t).strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("“") and t.endswith("”")):
        t = t[1:-1].strip()
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)
    t = t.replace("**", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return format_lines(t.strip())


# 문장 끝(. ! ? … 및 그 뒤/앞에 붙은 이모지) 다음의 공백에서 분리
_EMOJI = "\U0001F300-\U0001FAFF☀-➿"
_SENT_END = re.compile(rf"(?<=[.!?…])\s+(?=\S)|(?<=[.!?…][{_EMOJI}])\s+(?=\S)|(?<=[{_EMOJI}][.!?…])\s+(?=\S)")


def format_lines(text: str) -> str:
    """스레드 가독성용 줄바꿈: 한 문장 = 한 줄, 문단(빈 줄)은 유지. 3줄 넘는 문단은 3줄마다 빈 줄 삽입."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for p in paras:
        lines = []
        for raw in p.split("\n"):
            raw = raw.strip()
            if raw:
                lines += [x.strip() for x in _SENT_END.split(raw) if x.strip()]
        # 긴 문단은 3줄 단위로 끊어 숨 쉴 틈을 준다
        chunks = [lines[i:i + 3] for i in range(0, len(lines), 3)]
        out += ["\n".join(c) for c in chunks]
    return "\n\n".join(out)


# ---------------- 생성 ----------------
def generate_post(account_id: str, topic: dict | None = None) -> tuple[dict, str]:
    """(topic, body) 반환. body 는 링크가 붙기 전 순수 본문."""
    topic = topic or pick_topic(account_id)
    backend = get_backend()
    system = build_system(account_id)
    body = clean(backend.generate(system, build_user(topic)))
    if cfg["ai"].get("self_review", True):
        reviewed = clean(backend.generate(system, build_review(body, account_id)))
        if len(reviewed) > 40:
            body = reviewed
    max_chars = int(cfg["posting"].get("max_chars", 420))
    if len(body) > max_chars:
        # 문단 경계에서 자르기
        cut = body[:max_chars]
        pos = max(cut.rfind("\n\n"), cut.rfind(". "), cut.rfind("요."), cut.rfind("다."))
        body = cut[: pos + 2].strip() if pos > max_chars * 0.5 else cut.strip()
    return topic, body


# ---------------- 인스타그램 카드뉴스 ----------------
def build_card_slides(topic: dict, body: str) -> list[str]:
    """본문을 카드뉴스 본문 슬라이드(제목 제외) 텍스트로 요약해 리스트로 반환."""
    n = max(1, int((cfg.get("instagram") or {}).get("cards_per_post", 5)) - 1)
    backend = get_backend()
    system = "당신은 인스타그램 카드뉴스를 만드는 편집자입니다. 주어진 글을 짧고 임팩트 있는 카드 문장들로 요약합니다."
    user = f"""[본문]
{body}

위 내용을 인스타그램 카드뉴스 {n}장 분량으로 요약하세요.
- 한 장당 한 줄, 25자 내외로 짧고 임팩트 있게
- 이모지, 따옴표, 번호(1. 2. 등) 붙이지 말 것
- 정확히 {n}줄만 출력하고 그 외 설명은 절대 쓰지 말 것"""
    raw = backend.generate(system, user)
    lines = []
    for l in raw.splitlines():
        l = re.sub(r"^[\-\*\d\.\)\s]+", "", l.strip()).strip()
        l = l.strip('"“”').strip()
        if l:
            lines.append(l)
    lines = lines[:n]
    while len(lines) < n:
        lines.append((topic.get("title") or "")[:25] or "더 알아보기")
    return lines

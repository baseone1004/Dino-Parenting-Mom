"""글감 찾기 — Google 뉴스 RSS(키 불필요)에서 키워드별 헤드라인을 모아 AI 에게 주제 후보를 뽑게 한 뒤
'pending' 글감으로 저장. 대시보드에서 승인하면 다음 게시 때 topics.yaml 보다 먼저 사용됨."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

from app import store
from app.ai_backend import get_backend
from app.config import cfg, account_cfg
from app.generator import _read

RSS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_headlines(keyword: str, limit: int = 8) -> list[str]:
    try:
        r = requests.get(RSS.format(q=quote(keyword)), timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []
    titles = []
    for item in root.iter("item"):
        t = (item.findtext("title") or "").strip()
        t = re.sub(r"\s*-\s*[^-]+$", "", t)  # 끝의 " - 언론사" 제거
        if t:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def collect(account_id: str, n_ideas: int = 5) -> int:
    """헤드라인 수집 → AI 가 계정 성격에 맞는 글감 n개 제안 → pending 저장. 저장 개수 반환."""
    acc = account_cfg(account_id) or {}
    keywords = acc.get("trend_keywords") or []
    per = int(cfg["trend"].get("headlines_per_keyword", 8))
    heads: list[str] = []
    for k in keywords:
        heads += fetch_headlines(k, per)
    if not heads:
        store.log("WARN", "글감 수집: 헤드라인을 가져오지 못했습니다.", account_id)
        return 0

    profile = _read(account_id, "profile.md")
    system = "당신은 SNS 콘텐츠 기획자입니다. 반드시 지정된 형식으로만 답합니다."
    user = f"""아래 [프로필]의 사람이 Threads 에 쓸 글감을 요즘 뉴스 헤드라인에서 {n_ideas}개 뽑아주세요.
뉴스 요약이 아니라, 이 사람의 경험과 연결되는 '개인 이야기' 주제여야 합니다.
각 줄 형식(구분자는 |, 다른 말 금지):
주제 한 줄 | 관점/감정 | 관련 쿠팡 상품 키워드(없으면 빈칸)

[프로필]
{profile}

[헤드라인]
""" + "\n".join(f"- {h}" for h in heads)

    text = get_backend().generate(system, user)
    saved = 0
    for line in text.splitlines():
        if "|" not in line:
            continue
        parts = [p.strip(" -•*") for p in line.split("|")]
        title = parts[0]
        if len(title) < 5:
            continue
        angle = parts[1] if len(parts) > 1 and parts[1] else None
        product = parts[2] if len(parts) > 2 and parts[2] else None
        store.add_idea(account_id, title, angle, product, source="google-news")
        saved += 1
    store.log("INFO", f"글감 {saved}개 수집 (헤드라인 {len(heads)}개)", account_id)
    return saved

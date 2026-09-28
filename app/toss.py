"""토스쇼핑 쉐어링크 Open API — OAuth2 토큰, 상품 딥링크 발급.

승인 전에는 사용 불가 (config.yaml 의 toss.enabled: false 유지).
키 발급: 쉐어링크 크리에이터 어드민(sharelink.toss.im) > 사용 승인 신청 → 검수 → Access Key/Secret Key/publisherId 발급
문서: https://sharelink-docs.toss.im/ (Open API 연동 가이드)

topics.yaml 의 link: 필드에 쉐어링크 URL을 직접 붙여넣는 방식이 기본이며 (쿠팡과 동일한 방식),
이 모듈은 상품 ID(tacaItemId)를 알 때 그 링크 생성을 자동화하고 싶을 경우에만 사용합니다.
"""
from __future__ import annotations

import random
import time

import requests

from app.config import cfg, env

TOKEN_URL = "https://oauth2.cert.toss.im/token"
API_BASE = "https://sharelink.toss.im/openapi"

# 생활용품/주방용품/욕실용품 (식품·건강기능식품 없음) — sharelink.toss.im/openapi/categories 로 조회해 확정한 값.
# 34245(청소용품)는 best-categories 응답이 항상 비어 있어서 제외 (카테고리는 존재하지만 베스트셀러 집계가 안 되는 듯).
LIFESTYLE_CATEGORY_IDS = [29967, 23759]

_token_cache: dict = {"token": None, "expires_at": 0}


class TossError(RuntimeError):
    pass


def _keys() -> tuple[str, str, str]:
    ak, sk, pub = env("TOSS_ACCESS_KEY"), env("TOSS_SECRET_KEY"), env("TOSS_PUBLISHER_ID")
    if not ak or not sk or not pub:
        raise TossError(".env 에 TOSS_ACCESS_KEY / TOSS_SECRET_KEY / TOSS_PUBLISHER_ID 가 없습니다.")
    return ak, sk, pub


def _access_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    ak, sk, _ = _keys()
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials", "client_id": ak, "client_secret": sk,
        "scope": "sharelink:read sharelink:write",
    }, timeout=20)
    try:
        data = r.json()
    except ValueError:
        raise TossError(f"토큰 발급 응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200 or "access_token" not in data:
        raise TossError(f"토스 토큰 발급 오류 {r.status_code}: {data}")
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    return _token_cache["token"]


def _request(method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {_access_token()}"}
    r = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=20, **kwargs)
    try:
        data = r.json()
    except ValueError:
        raise TossError(f"응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200:
        raise TossError(f"토스 API 오류 {r.status_code}: {data}")
    return data


def link_for_item(taca_item_id: int | str, sub_tag: str | None = None) -> str:
    """상품 ID(tacaItemId)로 쉐어링크(딥링크) 발급."""
    _, _, publisher_id = _keys()
    body = {"tacaItemId": taca_item_id, "publisherId": publisher_id}
    data = _request("POST", "/links", json=body)
    success = data.get("success") or data
    url = success.get("shortUrl")
    if not url:
        raise TossError(f"쉐어링크 응답에 shortUrl 이 없습니다: {data}")
    return url


def pick_trending_product(category_ids: list[int] | None = None, size: int = 15) -> dict:
    """생활용품/주방용품/욕실용품 카테고리 중 하나에서 베스트셀러 상품을 무작위로 하나 골라 반환.
    {'tacaItemId', 'displayName', 'displayPrice'}. 품절 상품은 제외. 한 카테고리가 비어 있으면 다른 카테고리로 재시도."""
    category_ids = list(category_ids or cfg.get("toss", {}).get("category_ids") or LIFESTYLE_CATEGORY_IDS)
    random.shuffle(category_ids)
    for cid in category_ids:
        data = _request("GET", f"/products/best-categories/{cid}", params={"size": size})
        success = data.get("success") or data
        items = success.get("items") or []
        candidates = [it for it in items if not it.get("isSoldOut")]
        if candidates:
            return random.choice(candidates[: min(10, len(candidates))])
    raise TossError(f"카테고리 {category_ids} 어디에서도 판매 가능한 트렌드 상품을 찾지 못했습니다.")

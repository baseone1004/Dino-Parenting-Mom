"""쿠팡 파트너스 Open API — HMAC 서명, 상품 검색, 딥링크 생성.

키 발급: 쿠팡 파트너스 > 링크 생성 > API 키 발급 (Access Key / Secret Key) → .env
문서: https://partners.coupang.com/#help/open-api
"""
from __future__ import annotations

import hashlib
import hmac
import random
import time
from urllib.parse import urlencode, quote

import requests

from app.config import cfg, env

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi"


class CoupangError(RuntimeError):
    pass


def _keys() -> tuple[str, str]:
    ak, sk = env("COUPANG_ACCESS_KEY"), env("COUPANG_SECRET_KEY")
    if not ak or not sk:
        raise CoupangError(".env 에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 가 없습니다.")
    return ak, sk


def _auth_header(method: str, path: str, query: str = "") -> str:
    ak, sk = _keys()
    signed_date = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = signed_date + method + path + query
    signature = hmac.new(sk.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={ak}, signed-date={signed_date}, signature={signature}"


def _request(method: str, path: str, query: dict | None = None, body: dict | None = None) -> dict:
    qs = urlencode(query, quote_via=quote) if query else ""
    url = DOMAIN + path + (f"?{qs}" if qs else "")
    headers = {"Authorization": _auth_header(method, path, qs), "Content-Type": "application/json;charset=UTF-8"}
    r = requests.request(method, url, headers=headers, json=body, timeout=20)
    try:
        data = r.json()
    except ValueError:
        raise CoupangError(f"응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200 or str(data.get("rCode", "0")) != "0":
        raise CoupangError(f"쿠팡 API 오류 {r.status_code}: {data.get('rMessage') or data}")
    return data


def deeplink(coupang_url: str, sub_id: str | None = None) -> str:
    """일반 쿠팡 상품 URL → 파트너스 단축 링크."""
    sub_id = sub_id or cfg["coupang"].get("sub_id") or "threads"
    data = _request("POST", f"{BASE}/v1/deeplink", body={"coupangUrls": [coupang_url], "subId": sub_id})
    items = data.get("data") or []
    if not items:
        raise CoupangError("딥링크 응답이 비어 있습니다.")
    return items[0].get("shortenUrl") or items[0].get("landingUrl")


def search_products(keyword: str, limit: int = 3, sub_id: str | None = None) -> list[dict]:
    """키워드 검색. 반환 항목의 productUrl 은 이미 파트너스 추적 링크."""
    sub_id = sub_id or cfg["coupang"].get("sub_id") or "threads"
    data = _request("GET", f"{BASE}/products/search", query={"keyword": keyword, "limit": limit, "subId": sub_id})
    return (data.get("data") or {}).get("productData") or []


def link_for_keyword(keyword: str) -> str | None:
    """키워드로 검색해 첫 상품의 파트너스 링크(짧게 변환)를 돌려준다."""
    items = search_products(keyword, limit=1)
    if not items:
        return None
    url = items[0].get("productUrl")
    if not url:
        return None
    try:
        return deeplink(url)
    except CoupangError:
        return url


def best_category_products(category_id: int | str, limit: int = 20,
                           sub_id: str | None = None) -> list[dict]:
    """쿠팡 파트너스 카테고리 베스트 상품 목록."""
    sub_id = sub_id or cfg["coupang"].get("sub_id") or "threads"
    data = _request(
        "GET",
        f"{BASE}/v1/products/bestcategories/{category_id}",
        query={"limit": max(1, min(limit, 100)), "subId": sub_id},
    )
    return (data.get("data") or [])


def pick_trending_product(category_ids: list[int] | None = None, limit: int = 20) -> dict:
    """지정 카테고리 베스트 상위권에서 품절이 아닌 상품을 하나 선택한다."""
    ids = list(category_ids or [])
    random.shuffle(ids)
    for category_id in ids:
        items = best_category_products(category_id, limit=limit)
        candidates = [x for x in items if not x.get("isOutOfStock") and x.get("productUrl")]
        if candidates:
            # 늘 1위만 반복하지 않도록 상위 10개에서 선택한다.
            return random.choice(candidates[:10])
    raise CoupangError(f"카테고리 {ids}에서 판매 가능한 베스트 상품을 찾지 못했습니다.")


def pick_product_for_keywords(keywords: list[str], limit: int = 10) -> dict:
    """계정 성격에 맞는 검색어 하나로 상위 노출 상품을 조회해 선정한다.

    Search API는 시간당 10회 제한이 있으므로 호출자는 결과를 일 단위로 캐시해야 한다.
    """
    words = [str(x).strip() for x in keywords if str(x).strip()]
    if not words:
        raise CoupangError("자동 상품 검색어가 비어 있습니다.")
    keyword = random.choice(words)
    items = search_products(keyword, limit=limit)
    candidates = [x for x in items if x.get("productUrl")]
    if not candidates:
        raise CoupangError(f"'{keyword}' 검색 결과가 비어 있습니다.")
    # 검색 상단 관련성을 유지하면서 같은 상품 반복을 줄인다.
    return random.choice(candidates[: min(5, len(candidates))])

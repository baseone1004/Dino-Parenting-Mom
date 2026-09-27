"""Instagram Graph API — 연결된 페이스북 페이지의 액세스 토큰으로 호출.

게시 흐름(캐러셀): 이미지마다 컨테이너 생성(is_carousel_item=true) → 캐러셀 컨테이너 생성(children) →
                 게시(media_publish) → 댓글로 링크
주의: image_url 은 공개적으로 접근 가능한 URL 이어야 함 (Instagram 서버가 직접 다운로드).
문서: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/content-publishing
"""
from __future__ import annotations

import time

import requests

BASE = "https://graph.facebook.com/v19.0"


class InstagramError(RuntimeError):
    pass


def _call(method: str, path: str, **params) -> dict:
    r = requests.request(method, f"{BASE}{path}", params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=30)
    try:
        data = r.json()
    except ValueError:
        raise InstagramError(f"응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise InstagramError(f"Instagram API 오류 {r.status_code}: {err.get('message') or data} (code {err.get('code')})")
    return data


def create_carousel_item(ig_user_id: str, page_token: str, image_url: str) -> str:
    return _call("POST", f"/{ig_user_id}/media", image_url=image_url, is_carousel_item="true",
                access_token=page_token)["id"]


def create_carousel_container(ig_user_id: str, page_token: str, children_ids: list[str], caption: str) -> str:
    return _call("POST", f"/{ig_user_id}/media", media_type="CAROUSEL", children=",".join(children_ids),
                caption=caption, access_token=page_token)["id"]


def publish_container(ig_user_id: str, page_token: str, creation_id: str) -> str:
    return _call("POST", f"/{ig_user_id}/media_publish", creation_id=creation_id, access_token=page_token)["id"]


def comment_on_media(media_id: str, page_token: str, message: str) -> str:
    return _call("POST", f"/{media_id}/comments", message=message, access_token=page_token)["id"]


def publish_carousel_with_link(ig_user_id: str, page_token: str, image_urls: list[str], caption: str,
                               link_line: str | None) -> str:
    """카드뉴스 이미지들을 캐러셀로 게시하고, 있으면 링크를 댓글로 답니다. media id 반환."""
    if len(image_urls) < 2:
        raise InstagramError("캐러셀에는 이미지가 최소 2장 필요합니다.")
    children = []
    for url in image_urls:
        children.append(create_carousel_item(ig_user_id, page_token, url))
        time.sleep(1)  # 컨테이너 생성 처리 대기
    creation_id = create_carousel_container(ig_user_id, page_token, children, caption)
    time.sleep(3)
    media_id = publish_container(ig_user_id, page_token, creation_id)
    if link_line:
        time.sleep(3)
        comment_on_media(media_id, page_token, link_line)
    return media_id

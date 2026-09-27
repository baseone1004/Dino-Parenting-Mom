"""Facebook 페이지 API (graph.facebook.com).

게시 흐름: 피드 게시(POST /{page_id}/feed) → 댓글로 링크(POST /{post_id}/comments)
토큰:      사용자 토큰(대시보드에서 붙여넣기) → 관리 중인 페이지 목록 조회 → 페이지 액세스 토큰 저장
           (장기 사용자 토큰에서 얻은 페이지 토큰은 만료되지 않는 것이 일반적이나, 문서상 보장은 아님)
문서: https://developers.facebook.com/docs/pages-api / graph-api/reference/page/feed
"""
from __future__ import annotations

import requests

BASE = "https://graph.facebook.com/v19.0"


class FacebookError(RuntimeError):
    pass


def _call(method: str, path: str, **params) -> dict:
    r = requests.request(method, f"{BASE}{path}", params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=30)
    try:
        data = r.json()
    except ValueError:
        raise FacebookError(f"응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise FacebookError(f"Facebook API 오류 {r.status_code}: {err.get('message') or data} (code {err.get('code')})")
    return data


def list_pages(user_token: str) -> list[dict]:
    """사용자 토큰으로 관리 중인 페이지 목록. [{'id','name','access_token','instagram_business_account':{'id':..}}]"""
    d = _call("GET", "/me/accounts", fields="id,name,access_token,instagram_business_account", access_token=user_token)
    return d.get("data", [])


def publish_feed_post(page_id: str, page_token: str, message: str) -> str:
    """페이지 피드에 텍스트 글 게시. media id 반환."""
    return _call("POST", f"/{page_id}/feed", message=message, access_token=page_token)["id"]


def comment_on_post(post_id: str, page_token: str, message: str) -> str:
    """게시물에 댓글(텍스트만, 링크 미리보기 없음). comment id 반환."""
    return _call("POST", f"/{post_id}/comments", message=message, access_token=page_token)["id"]


def publish_with_link(page_id: str, page_token: str, body: str, link_line: str | None) -> str:
    """본문 게시 후, 있으면 링크를 댓글로 답니다. 페이지 게시물 id 반환."""
    post_id = publish_feed_post(page_id, page_token, body)
    if link_line:
        comment_on_post(post_id, page_token, link_line)
    return post_id

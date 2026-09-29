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
    """링크가 있으면 본문 끝에 붙여서 게시 (댓글 권한(pages_manage_engagement) 불필요). 페이지 게시물 id 반환."""
    message = f"{body}\n\n{link_line}" if link_line else body
    return publish_feed_post(page_id, page_token, message)


def publish_photo_with_link(page_id: str, page_token: str, body: str, image_url: str,
                            link_line: str | None) -> str:
    """대표 이미지 한 장을 공개 사진 게시물로 올린다.

    다중 attached_media 피드 게시물은 일부 New Pages Experience 페이지에서 API 성공 후에도
    사진 탭에만 남고 메인 피드에 표시되지 않는 경우가 있어, 피드 노출이 안정적인 /photos
    published=true 방식을 Facebook 기본 게시 경로로 사용한다.
    """
    message = f"{body}\n\n{link_line}" if link_line else body
    return _call("POST", f"/{page_id}/photos", url=image_url, published="true",
                 message=message, access_token=page_token)["post_id"]


def upload_unpublished_photo(page_id: str, page_token: str, image_url: str) -> str:
    """나중에 피드 게시물에 첨부할 사진을 미리 업로드 (아직 타임라인에 안 보임). photo id 반환."""
    return _call("POST", f"/{page_id}/photos", url=image_url, published="false", access_token=page_token)["id"]


def publish_multi_photo_with_link(page_id: str, page_token: str, body: str, image_urls: list[str],
                                  link_line: str | None) -> str:
    """사진 여러 장을 인스타그램 캐러셀처럼 한 게시물에 붙여서(다중 사진 게시물) 게시.
    링크가 있으면 본문 끝에 붙임 (댓글 권한(pages_manage_engagement) 불필요 — 사진이 이미 붙어있어
    링크 미리보기 썸네일은 뜨지 않음). 페이지 게시물 id 반환."""
    import json as _json
    photo_ids = [upload_unpublished_photo(page_id, page_token, url) for url in image_urls]
    media_params = {f"attached_media[{i}]": _json.dumps({"media_fbid": pid}) for i, pid in enumerate(photo_ids)}
    message = f"{body}\n\n{link_line}" if link_line else body
    return _call("POST", f"/{page_id}/feed", message=message, access_token=page_token, **media_params)["id"]

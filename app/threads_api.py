"""Threads 공식 API (graph.threads.net).

게시 흐름: 컨테이너 생성(POST /{user_id}/threads) → 게시(POST /{user_id}/threads_publish)
토큰:      단기 토큰 → 장기 토큰 교환(60일) → 만료 전 갱신(refresh)
문서: https://developers.facebook.com/docs/threads
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import requests

from app.config import env

BASE = "https://graph.threads.net/v1.0"


class ThreadsError(RuntimeError):
    pass


def _call(method: str, path: str, **params) -> dict:
    r = requests.request(method, f"{BASE}{path}", params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=30)
    try:
        data = r.json()
    except ValueError:
        raise ThreadsError(f"응답 파싱 실패 ({r.status_code}): {r.text[:200]}")
    if r.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise ThreadsError(f"Threads API 오류 {r.status_code}: {err.get('message') or data} (code {err.get('code')})")
    return data


def get_me(token: str) -> dict:
    """토큰 검증 겸 사용자 정보. {'id':..., 'username':...}"""
    return _call("GET", "/me", fields="id,username", access_token=token)


def create_text_container(user_id: str, token: str, text: str, reply_to_id: str | None = None) -> str:
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    return _call("POST", f"/{user_id}/threads", **params)["id"]


def publish_container(user_id: str, token: str, creation_id: str) -> str:
    return _call("POST", f"/{user_id}/threads_publish", creation_id=creation_id, access_token=token)["id"]


def publish_text(user_id: str, token: str, text: str, reply_to_id: str | None = None) -> str:
    """텍스트 글(또는 댓글) 게시 후 media id 반환."""
    cid = create_text_container(user_id, token, text, reply_to_id)
    time.sleep(3)  # 컨테이너 처리 대기 (권장)
    return publish_container(user_id, token, cid)


def publish_with_link(user_id: str, token: str, body: str, link_line: str | None, placement: str) -> str:
    """placement: body | reply | none"""
    if link_line and placement == "body":
        return publish_text(user_id, token, f"{body}\n\n{link_line}")
    post_id = publish_text(user_id, token, body)
    if link_line and placement == "reply":
        time.sleep(5)
        publish_text(user_id, token, link_line, reply_to_id=post_id)
    return post_id


def exchange_long_lived(short_token: str) -> tuple[str, datetime]:
    """단기 토큰(1시간) → 장기 토큰(60일). THREADS_APP_SECRET 필요."""
    secret = env("THREADS_APP_SECRET")
    if not secret:
        raise ThreadsError(".env 에 THREADS_APP_SECRET 이 없습니다.")
    d = _call("GET", "/access_token", grant_type="th_exchange_token", client_secret=secret, access_token=short_token)
    return d["access_token"], datetime.now() + timedelta(seconds=int(d.get("expires_in", 60 * 86400)))


def refresh_long_lived(token: str) -> tuple[str, datetime]:
    """장기 토큰 갱신 (발급 24시간 이후 ~ 만료 전에만 가능)."""
    d = _call("GET", "/refresh_access_token", grant_type="th_refresh_token", access_token=token)
    return d["access_token"], datetime.now() + timedelta(seconds=int(d.get("expires_in", 60 * 86400)))


def get_insights(media_id: str, token: str) -> dict:
    """게시글 성과. {'views':n,'likes':n,'replies':n,'reposts':n}"""
    d = _call("GET", f"/{media_id}/insights", metric="views,likes,replies,reposts", access_token=token)
    out = {}
    for m in d.get("data", []):
        vals = m.get("values") or []
        out[m["name"]] = int(vals[0].get("value", 0)) if vals else int((m.get("total_value") or {}).get("value", 0))
    return out

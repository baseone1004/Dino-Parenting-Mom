"""KIE.AI (api.kie.ai) 로 일상글용 카드뉴스 표지 이미지를 자동 생성.

문서: https://docs.kie.ai/flux-kontext-api/generate-or-edit-image
흐름: createTask(prompt) → taskId 받음 → recordInfo 폴링(state == success) → resultUrls[0]
"""
from __future__ import annotations

import time

import requests

from app.config import env

BASE = "https://api.kie.ai/api/v1"


class KieError(RuntimeError):
    pass


def _headers() -> dict:
    key = env("KIE_API_KEY")
    if not key:
        raise KieError(".env 의 KIE_API_KEY 가 없습니다.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def generate_image(prompt: str, aspect_ratio: str = "16:9", poll_interval: int = 5, timeout: int = 120) -> str:
    """프롬프트로 이미지 생성 후 완료될 때까지 기다렸다가 이미지 URL 반환."""
    r = requests.post(f"{BASE}/jobs/createTask", headers=_headers(), json={
        "model": "flux1-kontext",
        "input": {"prompt": prompt, "aspect_ratio": aspect_ratio, "output_format": "jpeg"},
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 200:
        raise KieError(f"KIE 작업 생성 실패: {data}")
    task_id = data["data"]["taskId"]

    waited = 0
    while waited < timeout:
        time.sleep(poll_interval)
        waited += poll_interval
        r = requests.get(f"{BASE}/jobs/recordInfo", headers=_headers(), params={"taskId": task_id}, timeout=30)
        r.raise_for_status()
        info = r.json().get("data", {})
        state = info.get("state")
        if state == "success":
            import json
            urls = json.loads(info.get("resultJson") or "{}").get("resultUrls") or []
            if not urls:
                raise KieError("KIE 작업 성공했지만 결과 이미지가 없습니다.")
            return urls[0]
        if state == "fail":
            raise KieError(f"KIE 이미지 생성 실패: {info.get('failMsg')}")
    raise KieError("KIE 이미지 생성 시간 초과")

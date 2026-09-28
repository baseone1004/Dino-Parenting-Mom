"""OpenAI 이미지 API(gpt-image-1)로 카드뉴스 이미지를 통째로 생성.

KIE.AI(flux1-kontext) + Google Slides 텍스트 오버레이 조합과 달리, 이 모델은 한글 텍스트를
이미지 안에 직접, 정확하게 그려 넣을 수 있어서 문구·뱃지·아이콘이 다 박힌 광고 카드뉴스를
한 번에 만들 수 있음.

- 실제 상품 사진이 있으면(product_image_url) images/edits 로 그 사진을 기반으로 문구/뱃지를
  추가 (상품 실물은 그대로 유지).
- 없으면 images/generations 로 처음부터 생성.

문서: https://platform.openai.com/docs/guides/image-generation
"""
from __future__ import annotations

import base64

import requests

from app.config import env

BASE = "https://api.openai.com/v1"
SIZE = "1024x1024"


class OpenAIImageError(RuntimeError):
    pass


def _headers() -> dict:
    key = env("OPENAI_API_KEY")
    if not key:
        raise OpenAIImageError(".env 의 OPENAI_API_KEY 가 없습니다.")
    return {"Authorization": f"Bearer {key}"}


def generate_image(prompt: str) -> bytes:
    """텍스트 프롬프트만으로 이미지를 새로 생성. PNG 바이트 반환."""
    r = requests.post(f"{BASE}/images/generations", headers=_headers(), json={
        "model": "gpt-image-1", "prompt": prompt, "size": SIZE, "quality": "medium",
    }, timeout=120)
    if r.status_code != 200:
        raise OpenAIImageError(f"OpenAI 이미지 생성 실패 {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


def edit_image(image_bytes: bytes, prompt: str) -> bytes:
    """실제 상품 사진을 기반으로 문구/뱃지를 추가해 편집. PNG 바이트 반환."""
    files = {"image": ("input.png", image_bytes, "image/png")}
    data = {"model": "gpt-image-1", "prompt": prompt, "size": SIZE, "quality": "medium"}
    r = requests.post(f"{BASE}/images/edits", headers=_headers(), files=files, data=data, timeout=120)
    if r.status_code != 200:
        raise OpenAIImageError(f"OpenAI 이미지 편집 실패 {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


def fetch_bytes(url: str, timeout: int = 15) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

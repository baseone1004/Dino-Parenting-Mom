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
import io

import requests
from PIL import Image

from app.config import env

BASE = "https://api.openai.com/v1"
# gpt-image-1 은 1024x1024 / 1024x1536 / 1536x1024 만 지원 — 세로형(4:5)에 가장 가까운
# 1024x1536(2:3)로 생성한 뒤 4:5(1024x1280)로 가운데를 잘라냄.
SIZE = "1024x1536"
TARGET_RATIO = (4, 5)


class OpenAIImageError(RuntimeError):
    pass


def _headers() -> dict:
    key = env("OPENAI_API_KEY")
    if not key:
        raise OpenAIImageError(".env 의 OPENAI_API_KEY 가 없습니다.")
    return {"Authorization": f"Bearer {key}"}


def _crop_to_ratio(png_bytes: bytes, ratio: tuple[int, int] = TARGET_RATIO) -> bytes:
    """가운데 기준으로 목표 비율(가로:세로)에 맞춰 잘라냄."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    target_w, target_h = ratio
    # 목표 비율보다 세로가 더 길면(=2:3 이 4:5 보다 김) 위아래를 잘라 높이를 줄인다.
    new_h = round(w * target_h / target_w)
    if new_h < h:
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    else:
        new_w = round(h * target_w / target_h)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def generate_image(prompt: str) -> bytes:
    """텍스트 프롬프트만으로 이미지를 새로 생성, 4:5 세로형으로 잘라서 PNG 바이트 반환."""
    r = requests.post(f"{BASE}/images/generations", headers=_headers(), json={
        "model": "gpt-image-1", "prompt": prompt, "size": SIZE, "quality": "medium",
    }, timeout=120)
    if r.status_code != 200:
        raise OpenAIImageError(f"OpenAI 이미지 생성 실패 {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return _crop_to_ratio(base64.b64decode(b64))


def edit_image(image_bytes: bytes, prompt: str) -> bytes:
    """실제 상품 사진을 기반으로 문구/뱃지를 추가해 편집, 4:5 세로형으로 잘라서 PNG 바이트 반환."""
    files = {"image": ("input.png", image_bytes, "image/png")}
    data = {"model": "gpt-image-1", "prompt": prompt, "size": SIZE, "quality": "medium"}
    r = requests.post(f"{BASE}/images/edits", headers=_headers(), files=files, data=data, timeout=120)
    if r.status_code != 200:
        raise OpenAIImageError(f"OpenAI 이미지 편집 실패 {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return _crop_to_ratio(base64.b64decode(b64))


def fetch_bytes(url: str, timeout: int = 15) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

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
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from app.config import env

BASE = "https://api.openai.com/v1"
# gpt-image-1 은 1024x1024 / 1024x1536 / 1536x1024 만 지원 — 세로형(4:5)에 가장 가까운
# 1024x1536(2:3)로 생성한 뒤 4:5(1024x1280)로 가운데를 잘라냄.
SIZE = "1024x1536"
TARGET_RATIO = (4, 5)

# 긴 한글 문장은 gpt-image-1 이 종종 오타를 내서(예: "만에"→"만애"), 부제목/체크리스트/CTA 는
# AI 가 그리지 않고 이 폰트로 직접, 정확하게 덧그림 — 짧은 제목만 AI 에게 맡김.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic-Bold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
]


def _korean_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise OpenAIImageError("한글 폰트를 찾을 수 없습니다 — 서버에 'sudo apt install -y fonts-nanum' 필요합니다.")


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
    # 목표 비율보다 세로가 더 길면(=2:3 이 4:5 보다 김) 아래쪽만 잘라 높이를 줄인다 — AI 가 그린
    # 제목/일러스트는 위쪽에 있고, 잘려도 되는 여백은 우리가 텍스트 패널을 덧그릴 아래쪽에 있음.
    new_h = round(w * target_h / target_w)
    if new_h < h:
        img = img.crop((0, 0, w, new_h))
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


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def compose_text_panel(img_bytes: bytes, subtitle: str, points: list[str], cta: str) -> bytes:
    """AI 가 비워둔 하단 영역에 부제목·체크리스트·CTA 를 정확한 폰트로 직접 그려 넣음."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    margin = int(w * 0.08)
    panel_top = int(h * 0.60)
    panel_bottom = int(h * 0.97)
    draw.rounded_rectangle([margin, panel_top, w - margin, panel_bottom], radius=28,
                           fill=(255, 255, 255, 235))

    pad = int(w * 0.05)
    x = margin + pad
    max_w = w - margin * 2 - pad * 2
    y = panel_top + pad

    subtitle_font = _korean_font(int(w * 0.042))
    point_font = _korean_font(int(w * 0.036))
    cta_font = _korean_font(int(w * 0.03))

    def draw_block(text: str, font: ImageFont.FreeTypeFont, fill: tuple, y: int) -> int:
        for line in _wrap_text(draw, text, font, max_w):
            draw.text((x, y), line, font=font, fill=fill)
            y += int(font.size * 1.35)
        return y

    if subtitle:
        y = draw_block(subtitle, subtitle_font, (70, 55, 45, 255), y) + int(h * 0.015)
    for p in points[:3]:
        if p:
            # "✓"/이모지는 NanumGothic 에 없어서 빈 네모(tofu)로 깨짐 — 폰트가 확실히 지원하는
            # 가운뎃점(•)으로 대체.
            y = draw_block(f"• {p}", point_font, (80, 65, 55, 255), y)
    if cta:
        y += int(h * 0.015)
        draw_block(cta, cta_font, (140, 120, 105, 255), y)

    out = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def fetch_bytes(url: str, timeout: int = 15) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

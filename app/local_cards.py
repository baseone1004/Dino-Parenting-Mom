"""외부 이미지 API가 실패해도 Instagram 게시를 계속할 수 있는 Pillow 카드 렌더러."""
from __future__ import annotations

import io
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.slides_cards import CARDS_DIR

WIDTH, HEIGHT = 1080, 1350
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    raise RuntimeError("한글 폰트가 없습니다. Ubuntu에서는 fonts-nanum 패키지를 설치하세요.")


def _wrap(text: str, width: int) -> str:
    """한국어도 공백이 적은 경우가 있어 글자 수 기준으로 안전하게 줄바꿈한다."""
    lines = []
    for paragraph in (text or "").splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=True,
                                   break_on_hyphens=False) or [""])
    return "\n".join(lines)


def _background(image_url: str | None, index: int) -> Image.Image:
    palette = [(255, 246, 238), (238, 248, 255), (242, 250, 241),
               (255, 242, 247), (247, 243, 255)]
    bg = Image.new("RGB", (WIDTH, HEIGHT), palette[index % len(palette)])
    if not image_url:
        return bg
    try:
        r = requests.get(image_url, timeout=15)
        r.raise_for_status()
        photo = Image.open(io.BytesIO(r.content)).convert("RGB")
        photo = ImageOps.fit(photo, (WIDTH, 650), method=Image.Resampling.LANCZOS)
        photo.putalpha(215)
        bg = bg.convert("RGBA")
        bg.alpha_composite(photo, (0, 0))
        return bg.convert("RGB")
    except Exception:
        return bg


def _draw_card(title: str, body: str, index: int, total: int,
               image_url: str | None) -> Image.Image:
    img = _background(image_url if index == 0 else None, index)
    draw = ImageDraw.Draw(img)
    accent = [(225, 111, 95), (73, 139, 191), (70, 151, 107),
              (204, 93, 138), (127, 100, 184)][index % 5]

    draw.rounded_rectangle((65, 65, WIDTH - 65, HEIGHT - 65), radius=42,
                           fill=(255, 255, 255), outline=accent, width=5)
    draw.rounded_rectangle((100, 100, 305, 158), radius=25, fill=accent)
    draw.text((128, 112), "오늘의 생활 팁", font=_font(27), fill="white")

    title_y = 220
    draw.multiline_text((110, title_y), _wrap(title, 15), font=_font(66), fill=(42, 42, 46),
                        spacing=15)
    body_y = 720 if index == 0 and image_url else 590
    draw.multiline_text((115, body_y), _wrap(body, 18), font=_font(48), fill=(66, 66, 72),
                        spacing=22)
    draw.text((110, HEIGHT - 145), "저장해두고 다시 확인하세요", font=_font(29), fill=accent)
    page = f"{index + 1} / {total}"
    draw.text((WIDTH - 110, HEIGHT - 140), page, font=_font(26), fill=(125, 125, 132), anchor="ra")
    return img


def render_cards(post_id: int, title: str, slide_texts: list[str],
                 cover_image_url: str | None = None) -> list[Path]:
    """표지 1장과 요약 본문 카드를 PNG로 만든다."""
    bodies = [slide_texts[0] if slide_texts else title] + list(slide_texts)
    total = len(bodies)
    out_dir = CARDS_DIR / str(post_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, body in enumerate(bodies):
        image = _draw_card(title if i == 0 else f"{title} · {i}", body, i, total,
                           cover_image_url)
        path = out_dir / f"{i + 1}.png"
        image.save(path, "PNG", optimize=True)
        paths.append(path)
    return paths

"""외부 이미지 API가 실패해도 Instagram 게시를 계속할 수 있는 Pillow 카드 렌더러."""
from __future__ import annotations

import io
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.slides_cards import CARDS_DIR

WIDTH, HEIGHT = 1080, 1350
PALETTES = {
    "aegitem": ((255, 247, 241), (235, 125, 116), (255, 223, 208), "육아템 기록"),
    "salimtem": ((247, 244, 235), (91, 132, 102), (220, 232, 211), "살림템 노트"),
    "kkultem": ((246, 242, 255), (119, 92, 178), (229, 218, 250), "오늘의 꿀템"),
}
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


def _background(image_url: str | None, color: tuple[int, int, int]) -> tuple[Image.Image, Image.Image | None]:
    bg = Image.new("RGB", (WIDTH, HEIGHT), color)
    photo = None
    if not image_url:
        return bg, photo
    try:
        r = requests.get(image_url, timeout=15)
        r.raise_for_status()
        photo = Image.open(io.BytesIO(r.content)).convert("RGB")
        photo = ImageOps.fit(photo, (390, 390), method=Image.Resampling.LANCZOS)
        return bg, photo
    except Exception:
        return bg, None


def _draw_card(title: str, body: str, index: int, total: int,
               image_url: str | None, account_id: str) -> Image.Image:
    base, accent, soft, brand = PALETTES.get(account_id, ((250, 247, 242), (202, 112, 88),
                                                          (243, 220, 207), "오늘의 생활 팁"))
    # 캐러셀의 모든 장에 같은 실제 상품 사진을 넣어 넘겨보는 동안 상품 맥락이 유지되게 한다.
    img, photo = _background(image_url, base)
    draw = ImageDraw.Draw(img)
    # 배경 장식과 카드 그림자로 SNS 피드에서 밋밋하지 않게 보이도록 구성한다.
    draw.ellipse((760, -130, 1180, 290), fill=soft)
    draw.ellipse((-170, 1040, 250, 1460), fill=soft)
    draw.rounded_rectangle((74, 78, WIDTH - 54, HEIGHT - 54), radius=52, fill=(221, 214, 205))
    draw.rounded_rectangle((54, 54, WIDTH - 74, HEIGHT - 78), radius=52, fill=(255, 255, 255))
    draw.rounded_rectangle((92, 95, 325, 158), radius=28, fill=accent)
    draw.text((122, 111), brand, font=_font(28), fill="white")

    if index == 0:
        draw.text((92, 215), "요즘 눈에 띄는 아이템", font=_font(31), fill=accent)
        draw.multiline_text((92, 280), _wrap(title, 13), font=_font(72), fill=(35, 35, 42), spacing=17)
        if photo:
            mask = Image.new("L", photo.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 389, 389), radius=42, fill=255)
            img.paste(photo, (595, 595), mask)
            draw.rounded_rectangle((595, 595, 985, 985), radius=42, outline=accent, width=5)
            draw.multiline_text((92, 665), _wrap(body, 9), font=_font(47), fill=(67, 67, 76), spacing=20)
        else:
            draw.rounded_rectangle((92, 650, 988, 1010), radius=38, fill=soft)
            draw.multiline_text((145, 730), _wrap(body, 17), font=_font(51), fill=(55, 55, 65), spacing=24)
    else:
        number = f"{index:02d}"
        draw.text((930, 185), number, font=_font(150), fill=soft, anchor="ra")
        draw.text((92, 235), f"POINT {number}", font=_font(32), fill=accent)
        draw.multiline_text((92, 320), _wrap(body, 14), font=_font(65), fill=(38, 38, 45), spacing=24)
        draw.line((92, 760, 988, 760), fill=soft, width=8)
        if photo:
            small = ImageOps.fit(photo, (280, 280), method=Image.Resampling.LANCZOS)
            mask = Image.new("L", small.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 279, 279), radius=34, fill=255)
            img.paste(small, (700, 810), mask)
            draw.rounded_rectangle((700, 810, 980, 1090), radius=34, outline=accent, width=4)
            draw.multiline_text((92, 825), _wrap(title, 13), font=_font(34),
                                fill=(105, 105, 115), spacing=16)
        else:
            draw.multiline_text((92, 825), _wrap(title, 20), font=_font(34),
                                fill=(105, 105, 115), spacing=16)

    draw.text((92, HEIGHT - 155), "저장해두고 다음 구매 전에 확인하세요", font=_font(28), fill=accent)
    page = f"{index + 1} / {total}"
    draw.text((WIDTH - 110, HEIGHT - 150), page, font=_font(26), fill=(125, 125, 132), anchor="ra")
    return img


def render_cards(post_id: int, title: str, slide_texts: list[str],
                 cover_image_url: str | None = None, account_id: str = "") -> list[Path]:
    """표지 1장과 요약 본문 카드를 PNG로 만든다."""
    bodies = [slide_texts[0] if slide_texts else title] + list(slide_texts)
    total = len(bodies)
    out_dir = CARDS_DIR / str(post_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, body in enumerate(bodies):
        image = _draw_card(title, body, i, total, cover_image_url, account_id)
        path = out_dir / f"{i + 1}.png"
        image.save(path, "PNG", optimize=True)
        paths.append(path)
    return paths

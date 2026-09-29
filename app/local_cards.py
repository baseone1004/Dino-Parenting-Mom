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
CHARACTER_FILES = {
    "kkultem": Path("assets/characters/kkultem_bee.png"),
    "aegitem": Path("assets/characters/home_woman.png"),
    "salimtem": Path("assets/characters/home_woman.png"),
}
SCENE_LABELS = ["오늘의 발견", "한눈에 보기", "써보면 달라요", "구매 전 체크", "저장해 둘 결론"]
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


def _character(account_id: str, size: int) -> Image.Image | None:
    """계정별 고정 캐릭터를 원형 스티커로 만든다. 원본 얼굴/캐릭터는 변형하지 않는다."""
    path = CHARACTER_FILES.get(account_id)
    if not path or not path.exists():
        return None
    src = Image.open(path).convert("RGB")
    if account_id == "kkultem":
        # 로고의 중앙 벌 캐릭터와 카트를 사용하고 하단 글자는 카드 본문과 겹치지 않게 제외.
        w, h = src.size
        src = src.crop((int(w * .27), int(h * .20), int(w * .73), int(h * .53)))
    else:
        # 여성 캐릭터의 얼굴과 상반신만 사용해 원본 로고 문구는 제외.
        w, h = src.size
        src = src.crop((int(w * .08), int(h * .04), int(w * .58), int(h * .78)))
    src = ImageOps.fit(src, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((3, 3, size - 4, size - 4), fill=255)
    sticker = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    sticker.paste(src, (0, 0), mask)
    ImageDraw.Draw(sticker).ellipse((3, 3, size - 4, size - 4), outline=(255, 255, 255, 255), width=12)
    return sticker


def _paste_rounded(canvas: Image.Image, source: Image.Image, box: tuple[int, int, int, int],
                   radius: int, outline: tuple[int, int, int]):
    fitted = ImageOps.fit(source, (box[2] - box[0], box[3] - box[1]), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", fitted.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fitted.width - 1, fitted.height - 1), radius=radius, fill=255)
    canvas.paste(fitted, box[:2], mask)
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius=radius, outline=outline, width=5)


def _draw_card(title: str, body: str, index: int, total: int,
               image_url: str | None, account_id: str) -> Image.Image:
    base, accent, soft, brand = PALETTES.get(account_id, ((250, 247, 242), (202, 112, 88),
                                                          (243, 220, 207), "오늘의 생활 팁"))
    # 상품은 유지하되 장마다 크롭·배치·캐릭터 위치를 달리해 복제 카드처럼 보이지 않게 한다.
    img, photo = _background(image_url, base)
    draw = ImageDraw.Draw(img)
    # 배경 장식과 카드 그림자로 SNS 피드에서 밋밋하지 않게 보이도록 구성한다.
    draw.ellipse((760, -130, 1180, 290), fill=soft)
    draw.ellipse((-170, 1040, 250, 1460), fill=soft)
    draw.rounded_rectangle((74, 78, WIDTH - 54, HEIGHT - 54), radius=52, fill=(221, 214, 205))
    draw.rounded_rectangle((54, 54, WIDTH - 74, HEIGHT - 78), radius=52, fill=(255, 255, 255))
    draw.rounded_rectangle((92, 95, 365, 158), radius=28, fill=accent)
    draw.text((122, 111), f"{brand} · {SCENE_LABELS[index % len(SCENE_LABELS)]}",
              font=_font(22), fill="white")
    character = _character(account_id, 300 if index else 380)

    if index == 0:
        draw.text((92, 215), "요즘 눈에 띄는 아이템", font=_font(31), fill=accent)
        draw.multiline_text((92, 280), _wrap(title, 13), font=_font(72), fill=(35, 35, 42), spacing=17)
        if photo:
            _paste_rounded(img, photo, (570, 600, 985, 1015), 42, accent)
            draw.multiline_text((92, 665), _wrap(body, 9), font=_font(47), fill=(67, 67, 76), spacing=20)
        else:
            draw.rounded_rectangle((92, 650, 988, 1010), radius=38, fill=soft)
            draw.multiline_text((145, 730), _wrap(body, 17), font=_font(51), fill=(55, 55, 65), spacing=24)
        if character:
            img.paste(character, (675, 955), character)
    else:
        number = f"{index:02d}"
        draw.text((930, 185), number, font=_font(150), fill=soft, anchor="ra")
        draw.text((92, 235), f"POINT {number}", font=_font(32), fill=accent)
        draw.multiline_text((92, 320), _wrap(body, 14), font=_font(65), fill=(38, 38, 45), spacing=24)
        draw.line((92, 760, 988, 760), fill=soft, width=8)
        if photo:
            layouts = [
                ((650, 790, 980, 1120), (80, 905)),
                ((90, 790, 430, 1130), (475, 885)),
                ((610, 805, 985, 1090), (80, 890)),
                ((105, 800, 445, 1140), (480, 900)),
            ]
            photo_box, text_xy = layouts[(index - 1) % len(layouts)]
            _paste_rounded(img, photo, photo_box, 34, accent)
            draw.multiline_text(text_xy, _wrap(title, 13), font=_font(34),
                                fill=(105, 105, 115), spacing=16)
        else:
            draw.multiline_text((92, 825), _wrap(title, 20), font=_font(34),
                                fill=(105, 105, 115), spacing=16)
        if character:
            positions = [(80, 1010), (750, 1015), (75, 1005), (745, 1000)]
            pos = positions[(index - 1) % len(positions)]
            img.paste(character, pos, character)

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

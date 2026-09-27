"""프로필 이미지 생성 (1024x1024 PNG, 인스타/스레드 공용).

    python scripts/make_profile_images.py
→ assets/profile/aegitem.png, salimtem.png (+ 각 3가지 색상 변형)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "profile"
OUT.mkdir(parents=True, exist_ok=True)
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"
FONT_REG = "C:/Windows/Fonts/malgun.ttf"
SIZE = 1024

# 계정별 (메인 글자, 서브 문구, 색상 변형 [배경, 글자, 포인트])
ACCOUNTS = {
    "aegitem": ("애기템", "기록하는 엄마", [
        ("#FFE8D6", "#5B3A29", "#F4A261"),   # 피치
        ("#FDE2E4", "#6B2D3E", "#E07A8C"),   # 핑크
        ("#E8F1F2", "#2F4858", "#7FB3C8"),   # 민트블루
    ]),
    "salimtem": ("살림템", "골라주는 언니", [
        ("#E9F5DB", "#2F4A1E", "#7CB342"),   # 그린
        ("#FFF3C4", "#5A4500", "#F2B705"),   # 옐로
        ("#EDE7F6", "#3E2A6B", "#9575CD"),   # 라벤더
    ]),
}


def font(path, size):
    return ImageFont.truetype(path, size)


def draw_one(main: str, sub: str, bg: str, fg: str, accent: str) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), bg)
    d = ImageDraw.Draw(img)

    # 포인트 원 (오른쪽 위, 살짝 잘리게) + 바닥 띠
    d.ellipse((SIZE * 0.62, -SIZE * 0.18, SIZE * 1.18, SIZE * 0.38), fill=accent)
    d.rounded_rectangle((SIZE * 0.20, SIZE * 0.80, SIZE * 0.80, SIZE * 0.85), radius=40, fill=accent)

    # 메인 글자 (anchor='mm' 로 정중앙 기준 배치)
    f_main = font(FONT_BOLD, 300)
    cx, cy = SIZE / 2, SIZE * 0.44
    d.text((cx + 8, cy + 8), main, font=f_main, fill=accent, anchor="mm")
    d.text((cx, cy), main, font=f_main, fill=fg, anchor="mm")

    # 서브 문구
    f_sub = font(FONT_REG, 84)
    d.text((cx, SIZE * 0.67), sub, font=f_sub, fill=fg, anchor="mm")

    # 원형 마스크 미리보기용은 플랫폼이 알아서 자르므로 정사각형 그대로 저장
    return img


def main():
    for acc, (m, s, variants) in ACCOUNTS.items():
        for i, (bg, fg, ac) in enumerate(variants, 1):
            img = draw_one(m, s, bg, fg, ac)
            name = f"{acc}.png" if i == 1 else f"{acc}_v{i}.png"
            img.save(OUT / name, optimize=True)
            print("saved", OUT / name)


if __name__ == "__main__":
    main()

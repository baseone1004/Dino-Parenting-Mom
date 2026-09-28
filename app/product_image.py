"""쿠팡/토스 등 짧은 링크를 따라가서 상품 페이지의 대표 이미지(og:image)를 가져옵니다."""
from __future__ import annotations

import re

import requests

_OG_IMAGE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_IMAGE_REV = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)


def fetch_og_image(url: str, timeout: int = 10) -> str | None:
    """짧은 링크를 따라가서 최종 페이지의 og:image URL 을 반환. 실패하면 None."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        html = r.text[:200000]
        m = _OG_IMAGE.search(html) or _OG_IMAGE_REV.search(html)
        return m.group(1) if m else None
    except Exception:
        return None

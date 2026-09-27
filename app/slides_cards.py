"""Google Slides API 로 카드뉴스 이미지 생성 (인스타그램용).

템플릿 프레젠테이션(SLIDES_TEMPLATE_ID)은 미리 만들어 공유해 둬야 함 — scripts/setup_google_slides.md 참고.
  1번 슬라이드: {{TITLE}} 플레이스홀더 텍스트
  2번 슬라이드부터: {{BODY1}}, {{BODY2}}, ... 플레이스홀더 (config.yaml 의 instagram.cards_per_post - 1 장만큼)
서비스 계정 이메일에 그 프레젠테이션을 '편집자'로 공유해둬야 접근 가능.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import DATA_DIR, env

SCOPES = ["https://www.googleapis.com/auth/presentations", "https://www.googleapis.com/auth/drive"]
CARDS_DIR = DATA_DIR / "cards"
CARDS_DIR.mkdir(exist_ok=True)


class SlidesError(RuntimeError):
    pass


def _services():
    path = env("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not path or not Path(path).exists():
        raise SlidesError(".env 의 GOOGLE_SERVICE_ACCOUNT_FILE 이 없거나 파일을 찾을 수 없습니다.")
    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return (build("slides", "v1", credentials=creds, cache_discovery=False),
            build("drive", "v3", credentials=creds, cache_discovery=False))


def render_cards(post_id: int, title: str, slide_texts: list[str]) -> list[Path]:
    """제목 1장 + 본문 slide_texts 장을 PNG 로 렌더링해 data/cards/<post_id>/ 에 저장, 경로 목록 반환."""
    template_id = env("SLIDES_TEMPLATE_ID")
    if not template_id:
        raise SlidesError(".env 의 SLIDES_TEMPLATE_ID 가 없습니다.")
    slides_svc, drive_svc = _services()

    copy = drive_svc.files().copy(fileId=template_id, body={"name": f"card-{post_id}-{int(time.time())}"}).execute()
    copy_id = copy["id"]
    try:
        reqs = [{"replaceAllText": {"containsText": {"text": "{{TITLE}}", "matchCase": True}, "replaceText": title}}]
        for i, text in enumerate(slide_texts, start=1):
            reqs.append({"replaceAllText": {"containsText": {"text": f"{{{{BODY{i}}}}}", "matchCase": True},
                                            "replaceText": text}})
        slides_svc.presentations().batchUpdate(presentationId=copy_id, body={"requests": reqs}).execute()

        pres = slides_svc.presentations().get(presentationId=copy_id).execute()
        pages = pres.get("slides", [])
        n = 1 + len(slide_texts)
        out_dir = CARDS_DIR / str(post_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, page in enumerate(pages[:n], start=1):
            thumb = slides_svc.presentations().pages().getThumbnail(
                presentationId=copy_id, pageObjectId=page["objectId"],
                **{"thumbnailProperties.thumbnailSize": "LARGE"},
            ).execute()
            img = requests.get(thumb["contentUrl"], timeout=30)
            img.raise_for_status()
            p = out_dir / f"{i}.png"
            p.write_bytes(img.content)
            paths.append(p)
        if len(paths) < n:
            raise SlidesError(f"템플릿 슬라이드 수({len(pages)})가 필요한 장수({n})보다 적습니다.")
        return paths
    finally:
        try:
            drive_svc.files().delete(fileId=copy_id).execute()
        except Exception:
            pass

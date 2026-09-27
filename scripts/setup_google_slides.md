# 인스타그램 카드뉴스 이미지 자동 생성 (Google Slides API) 설정 가이드

인스타그램은 이미지 없이 글만 올릴 수 없어서, 본문을 요약한 카드뉴스 이미지를 **Google Slides API** 로
매번 자동 생성합니다. 한 번만 설정하면 됩니다 (15분).

## 1. Google Cloud 프로젝트 + API 활성화
1. https://console.cloud.google.com/ 접속 → 새 프로젝트 만들기 (이름 아무거나, 예: `sns-auto`)
2. **API 및 서비스 > 라이브러리** 에서 아래 두 개 검색해서 각각 **사용 설정**:
   - Google Slides API
   - Google Drive API

## 2. 서비스 계정 만들기
1. **API 및 서비스 > 사용자 인증 정보 > 사용자 인증 정보 만들기 > 서비스 계정**
2. 이름 아무거나 (예: `card-generator`) → 만들고 계속하기 → 역할은 건너뛰어도 됨 → 완료
3. 만들어진 서비스 계정 클릭 → **키** 탭 → **키 추가 > 새 키 만들기 > JSON** → 다운로드
4. 다운로드된 `.json` 파일을 프로젝트 폴더 안 아무 곳(예: `secrets/google-service-account.json`)에 저장
5. `.env` 의 `GOOGLE_SERVICE_ACCOUNT_FILE=` 에 그 파일의 전체 경로 입력
   - **이 폴더는 git 에 올리지 마세요** (`.gitignore` 확인)
6. 서비스 계정 이메일(예: `card-generator@sns-auto-123456.iam.gserviceaccount.com`)을 메모해두세요 — 4번에서 필요합니다.

## 3. 카드뉴스 템플릿 만들기
1. https://slides.google.com/ 에서 새 프레젠테이션 만들기 (제목 아무거나, 예: `카드뉴스 템플릿`)
2. **슬라이드 수 = `config.yaml` 의 `instagram.cards_per_post` 값** 만큼 만들기 (기본 5장)
3. 원하는 디자인(배경색, 폰트, 로고 등)을 자유롭게 꾸미되, 텍스트 상자에 아래 **플레이스홀더 문구를 정확히 그대로** 입력:
   - 1번 슬라이드: 제목 텍스트 상자에 `{{TITLE}}`
   - 2번 슬라이드: 본문 텍스트 상자에 `{{BODY1}}`
   - 3번 슬라이드: `{{BODY2}}`
   - 4번 슬라이드: `{{BODY3}}`
   - 5번 슬라이드: `{{BODY4}}`
   (슬라이드 장수를 바꾸려면 `config.yaml` 의 `instagram.cards_per_post` 도 같이 바꾸고, 템플릿 슬라이드 수/플레이스홀더 번호를 맞추세요)
4. 우측 상단 **공유** → 2번에서 메모한 **서비스 계정 이메일**을 추가하고 권한을 **편집자**로 설정
5. 주소창 URL 에서 프레젠테이션 ID 복사
   `https://docs.google.com/presentation/d/`**`이 부분`**`/edit`
6. `.env` 의 `SLIDES_TEMPLATE_ID=` 에 붙여넣기

## 4. 확인
- 파이썬 콘솔이나 `python -c` 로 직접 테스트:
  ```
  python -c "from app.slides_cards import render_cards; print(render_cards(999, '테스트 제목', ['본문1','본문2','본문3','본문4']))"
  ```
- `data/cards/999/` 폴더에 PNG 4~5장이 생기면 성공. 이미지를 열어서 플레이스홀더 대신 실제 텍스트가 들어갔는지 확인.

## 자주 나는 오류
| 메시지 | 원인 / 해결 |
|---|---|
| `The caller does not have permission` | 3-4번에서 템플릿을 서비스 계정 이메일에 공유 안 함 |
| `GOOGLE_SERVICE_ACCOUNT_FILE 이 없거나 파일을 찾을 수 없습니다` | `.env` 경로가 틀렸거나 상대경로 문제 — 절대경로로 입력 |
| `템플릿 슬라이드 수(N)가 필요한 장수(M)보다 적습니다` | 템플릿 슬라이드 수와 `cards_per_post` 를 맞추지 않음 |
| API 활성화 안 됨 오류 | 1번에서 Slides API/Drive API 둘 다 켰는지 확인 (몇 분 정도 반영 지연될 수 있음) |

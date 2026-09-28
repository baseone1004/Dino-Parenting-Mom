# 인스타그램 카드뉴스 이미지 자동 생성 (Google Slides API) 설정 가이드

인스타그램은 이미지 없이 글만 올릴 수 없어서, 본문을 요약한 카드뉴스 이미지를 **Google Slides API** 로
매번 자동 생성합니다. 한 번만 설정하면 됩니다 (15분).

## 1. Google Cloud 프로젝트 + API 활성화
1. https://console.cloud.google.com/ 접속 → 새 프로젝트 만들기 (이름 아무거나, 예: `sns-auto`)
2. **API 및 서비스 > 라이브러리** 에서 아래 두 개 검색해서 각각 **사용 설정**:
   - Google Slides API
   - Google Drive API

## 2. OAuth 클라이언트 만들기 (서비스 계정 대신 — 개인 Gmail 은 서비스 계정 Drive 용량이 0이라 파일 복사가 막힘)
1. **API 및 서비스 > OAuth 동의 화면** 에서 앱 이름/이메일만 채우고 "테스트" 상태로 게시 (외부 사용자 유형, 본인 이메일을 테스트 사용자로 추가)
2. **API 및 서비스 > 사용자 인증 정보 > 사용자 인증 정보 만들기 > OAuth 클라이언트 ID**
3. 애플리케이션 유형: **데스크톱 앱** → 이름 아무거나 → 만들기
4. 발급된 **클라이언트 ID**, **클라이언트 보안 비밀**을 메모
5. 아래 인가 URL 을 브라우저 주소창에 붙여넣고(`YOUR_CLIENT_ID` 를 4번 값으로 교체) 접속 → 본인 구글 계정으로 로그인 → 허용:
   ```
   https://accounts.google.com/o/oauth2/v2/auth?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:8080/&response_type=code&scope=https://www.googleapis.com/auth/presentations%20https://www.googleapis.com/auth/drive&access_type=offline&prompt=consent
   ```
6. 허용 후 `localhost:8080` 으로 연결 실패 페이지가 뜨는 게 정상 — **주소창 URL 에서 `code=` 뒤의 값**을 복사
7. 아래 명령으로 리프레시 토큰 교환 (`YOUR_CLIENT_ID`/`YOUR_CLIENT_SECRET`/`AUTH_CODE` 교체):
   ```bash
   curl -s -X POST https://oauth2.googleapis.com/token \
     -d client_id=YOUR_CLIENT_ID -d client_secret=YOUR_CLIENT_SECRET \
     -d code=AUTH_CODE -d grant_type=authorization_code \
     -d redirect_uri=http://localhost:8080/
   ```
8. 응답 JSON 의 `refresh_token` 값을 `.env` 의 `GOOGLE_OAUTH_REFRESH_TOKEN=` 에, 클라이언트 ID/보안 비밀을 각각
   `GOOGLE_OAUTH_CLIENT_ID=` / `GOOGLE_OAUTH_CLIENT_SECRET=` 에 저장

## 3. 카드뉴스 템플릿 만들기
1. https://slides.google.com/ 에서 새 프레젠테이션 만들기 (제목 아무거나, 예: `카드뉴스 템플릿`) — 본인 계정 소유라 별도 공유 불필요
2. **슬라이드 수 = `config.yaml` 의 `instagram.cards_per_post` 값** 만큼 만들기 (기본 5장)
3. 원하는 디자인(배경색, 폰트, 로고, 사진 등)을 자유롭게 꾸미되, 텍스트 상자에 아래 **플레이스홀더 문구를 정확히 그대로** 입력:
   - 1번 슬라이드: 제목 텍스트 상자에 `{{TITLE}}`
   - 2번 슬라이드: 본문 텍스트 상자에 `{{BODY1}}`
   - 3번 슬라이드: `{{BODY2}}`
   - 4번 슬라이드: `{{BODY3}}`
   - 5번 슬라이드: `{{BODY4}}`
   (슬라이드 장수를 바꾸려면 `config.yaml` 의 `instagram.cards_per_post` 도 같이 바꾸고, 템플릿 슬라이드 수/플레이스홀더 번호를 맞추세요)
4. 주소창 URL 에서 프레젠테이션 ID 복사
   `https://docs.google.com/presentation/d/`**`이 부분`**`/edit`
5. `.env` 의 `SLIDES_TEMPLATE_ID=` 에 붙여넣기

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

# Threads API 토큰 발급 가이드 (한 번만 하면 됨)

프로그램이 내 계정 대신 글을 올리려면 Meta 개발자 앱에서 **액세스 토큰**을 받아야 합니다.
로그인·권한 승인은 반드시 본인이 직접 해야 합니다. 15분 정도 걸립니다.

## 0. 준비
- Threads 계정 (Instagram 계정과 연결된 것)
- Facebook 계정 (개발자 사이트 로그인용)

## 1. Meta 개발자 앱 만들기
1. https://developers.facebook.com/ 접속 → 로그인 → 우측 상단 **내 앱** → **앱 만들기**
2. 사용 사례에서 **"Threads API 액세스"** 선택 (없으면 "기타" → 앱 유형 "비즈니스")
3. 앱 이름 아무거나 (예: `threads-auto`) → 만들기
4. 왼쪽 메뉴 **사용 사례 > Threads API > 설정(사용자 지정)** 에서 권한 추가:
   - `threads_basic`
   - `threads_content_publish`
   - `threads_manage_replies` (링크를 첫 댓글에 달기 위해 필요 — 기본 설정)
   - `threads_manage_insights` (조회수·좋아요 수집에 필요)
5. **앱 설정 > 기본 설정** 에서 **앱 시크릿 코드** 복사 → 프로젝트 `.env` 의 `THREADS_APP_SECRET=` 에 붙여넣기
   (단기 토큰을 장기 토큰으로 바꿀 때 필요. 대시보드에서 "장기 토큰" 을 바로 넣을 거면 생략 가능)

## 2. 테스트 사용자로 내 Threads 계정 등록
1. **앱 역할 > 역할** → **사람 추가** → "Threads 테스터" → 내 Threads 사용자명 입력
2. Threads 앱에서: **설정 > 계정 > 웹사이트 권한 > 초대** 에서 초대 수락
   (앱을 "라이브" 로 전환하고 앱 검수를 받으면 테스터 등록 없이도 되지만, 개인 용도는 테스터 방식이 가장 빠름)

## 3. 토큰 발급
### 방법 A: Graph API 탐색기 (가장 쉬움)
1. https://developers.facebook.com/tools/explorer/ 접속
2. 우측 상단 **Meta 앱** 에서 방금 만든 앱 선택
3. **사용자 또는 페이지** → **Threads 사용자 토큰 받기** (Get Threads User Token)
4. 권한 체크: `threads_basic`, `threads_content_publish`, `threads_manage_replies`, `threads_manage_insights` → **토큰 생성** → 로그인/승인
5. 생성된 토큰 복사. 이것은 **단기 토큰(1시간)** 입니다.
6. 대시보드(http://127.0.0.1:5000) → 계정 → **토큰 입력/교체** → 붙여넣고 종류를 **"단기 토큰 → 장기로 교환"** 선택 → 저장
   → 프로그램이 자동으로 60일짜리 장기 토큰으로 바꿔 저장하고 만료일을 계산합니다.
   (이 방법은 `.env` 의 `THREADS_APP_SECRET` 이 필요)

### 방법 B: 브라우저 주소창으로 직접 (앱 시크릿 없이)
1. 아래 주소에서 `APP_ID`, `REDIRECT_URI` 를 바꿔 브라우저에서 열기
   (`REDIRECT_URI` 는 앱 설정 > Threads API > "리디렉션 콜백 URL" 에 등록한 주소. 예: `https://localhost/`)
   ```
   https://threads.net/oauth/authorize?client_id=APP_ID&redirect_uri=REDIRECT_URI&scope=threads_basic,threads_content_publish,threads_manage_replies,threads_manage_insights&response_type=code
   ```
2. 승인 후 이동한 주소의 `?code=XXXX#_` 에서 `XXXX` 복사 (`#_` 제외)
3. 터미널에서 (curl 이 없으면 PowerShell `Invoke-RestMethod` 사용):
   ```
   curl -X POST https://graph.threads.net/oauth/access_token -d "client_id=APP_ID" -d "client_secret=APP_SECRET" -d "grant_type=authorization_code" -d "redirect_uri=REDIRECT_URI" -d "code=XXXX"
   ```
   → `access_token` (단기) 획득
4. 장기 토큰으로 교환:
   ```
   curl "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=APP_SECRET&access_token=단기토큰"
   ```
   → 60일짜리 `access_token`
5. 대시보드에서 **"장기 토큰(60일)"** 으로 저장

## 4. 확인
- 대시보드 계정 표에 `@사용자명` 과 `정상 (N일 남음)` 이 보이면 성공
- 테스트 모드에서 **초안 1개 생성** → 마음에 들면 **지금 게시** 로 1건만 실제 게시해 Threads 앱에서 확인

## 5. 토큰 만료 (60일)
- 프로그램이 매일 03:30 에 만료 7일 전부터 자동 갱신을 시도합니다 (발급 24시간 후 ~ 만료 전에만 가능).
- 대시보드에 **만료 N일 전** 경고가 계속 남아 있으면 갱신이 실패한 것 → 3번 과정으로 다시 발급.
- 만료를 넘기면 갱신이 불가능하므로 새로 발급해야 합니다.

## 자주 나는 오류
| 메시지 | 원인 / 해결 |
|---|---|
| `Invalid OAuth access token` | 토큰 오타/만료. 다시 발급 |
| `(#10) Application does not have permission` | 권한(`threads_content_publish`) 미체크 또는 테스터 초대 미수락 |
| `Unsupported post request` / `user_id` 오류 | 토큰이 Threads 용이 아닌 Facebook 용. "Threads 사용자 토큰 받기" 로 다시 |
| 하루 게시 한도 | Threads API 는 24시간에 250개 제한. 이 프로그램은 계정당 하루 3~5개만 |

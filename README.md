# Threads·페이스북·인스타그램 자동 게시 + 쿠팡 파트너스

주제 목록을 순환하며 OpenAI GPT가 내 말투로 글을 쓰고, 설정한 시각에 **Threads·페이스북 페이지·인스타그램**
세 곳에 동시에 자동 게시하며, 링크는 댓글로만 붙인다(본문/게시물에는 이미지 없는 순수 텍스트+링크 문구만).
인스타그램은 고정 캐릭터를 사용하는 로컬 카드 렌더러로 5장 캐러셀을 만든다. 글 생성용 API 키를 넣어도 이미지 생성 방식은 바뀌지 않는다.
대시보드에서 초안 확인·게시·계정 관리.

```
주제(topics.yaml) → GPT 글 생성(rules.md + profile.md) → 자가 검수 → 제휴 링크 →
   테스트 모드: 초안 저장   /   실전 모드: Threads + Facebook + Instagram(카드뉴스) 게시  →  대시보드
```

- Threads / Facebook: 같은 본문 그대로 게시, 링크는 댓글로 (미리보기 썸네일 없이 텍스트만)
- Instagram: 본문을 카드뉴스 4~5장으로 요약해 캐러셀 게시, 링크는 댓글로 (인스타 댓글은 원래 미리보기가 안 붙음)
- 세 플랫폼은 서로 독립적으로 시도됨 — 하나 실패해도 나머지는 정상 게시, 대시보드에서 실패한 플랫폼만 재시도 가능

## 1. 설치 (한 번)
```bash
pip install -r requirements.txt
```
- `.env`의 `OPENAI_API_KEY`를 입력하고 `config.yaml`의 `ai.backend: openai`로 실행한다. 기본 글 생성 모델은 `gpt-5-mini`다.
- API 인증·네트워크·한도 오류가 나면 내장 예비 본문과 카드 문구로 이어간다. ChatGPT 구독과 API 사용료는 별도다.
- 새 설치에서만 `.env.example`을 `.env`로 복사한다. 기존 `.env`와 운영 서버 토큰을 덮어쓰지 않는다.

## 2. 실행
```bash
python -m app.main
```
→ http://127.0.0.1:5000 대시보드. 창을 닫으면 멈추므로, 항상 켜두려면 3번 참고.

## 3. 컴퓨터 잠자기 상태에서도 게시되게 (한 번만, 관리자 PowerShell)
```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\register_wake.ps1
Start-ScheduledTask -TaskName ThreadsAutoPost
```
- 로그온 시 자동 시작 + 게시 시각 3분 전 자동 깨우기 + 절전 타이머 허용까지 한 번에 등록
- 컴퓨터를 **종료하지 말고 절전**으로 두면 됩니다. 완전히 끈 상태에서는 게시되지 않습니다 (그게 필요하면 클라우드 서버로 이전).
- 해제: `.\scripts\register_wake.ps1 -Remove`

## 4. 처음 세팅 순서 (영상과 동일)
1. **Threads 토큰 발급** → [scripts/setup_token.md](scripts/setup_token.md) → 대시보드 계정 표에서 입력
1-1. **페이스북 페이지 + 인스타그램 연결** → [scripts/setup_facebook.md](scripts/setup_facebook.md) → 대시보드에서 페이지 선택
1-2. **인스타그램 카드뉴스 이미지 생성 설정** → [scripts/setup_google_slides.md](scripts/setup_google_slides.md) (Google Slides API, 템플릿 프레젠테이션 1회 제작)
1-3. **인스타그램 실전 게시는 클라우드 서버 배포 후에만 가능** (9번 참고) — 이미지가 공개 URL로 열려야 해서 로컬 PC(127.0.0.1)에서는 게시 안 됨. `config.yaml` 의 `dashboard.public_base_url` 에 서버 주소 입력 필요
2. **쿠팡 링크** — 두 가지 중 하나
   - (지금) 파트너스 사이트 > **링크 생성** 에서 상품 링크 만들기 → `topics.yaml` 해당 주제의 `link:` 에 붙여넣기. API 키 불필요.
   - (최종 승인 후) API 키 발급 → `.env` 의 `COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY` + `config.yaml` 의 `coupang.use_api: true` → `product:` 키워드만으로 링크 자동 생성
   - 현재 자동상품 계정 설정: 육아템은 출산·유아동 베스트, 살림템은 주방·생활용품 베스트를 매일 07:30 한 번 조회해 사용합니다. 자세한 설정은 [scripts/setup_coupang.md](scripts/setup_coupang.md).
   - 꿀템로그는 토스쇼핑 베스트 상품을 같은 방식으로 하루 한 번 선정합니다.
3. **내 이야기로 바꾸기** → `accounts/demo/profile.md`(나는 누구인가), `topics.yaml`(주제 20개), `rules.md`(말투 규칙)
4. **테스트 모드로 2~3일** → 대시보드에서 초안 읽어보고 마음에 안 드는 패턴은 `rules.md` 에 금지 규칙 추가
5. 마음에 들면 **실전으로 전환** 버튼 → 이후 스케줄 시각마다 자동 게시
6. `config.yaml` 의 `link_after_days`(기본 14) 동안은 링크 없이 경험담만 올라가고, 그 뒤부터 쿠팡 링크가 붙음

## 5. 계정 추가 (여러 개 돌리기)
1. `accounts/demo` 폴더를 `accounts/<새id>` 로 복사하고 세 파일 수정
2. `config.yaml` 의 `accounts:` 에 항목 추가 (`id` 는 폴더명과 동일)
3. 프로그램 재시작 → 대시보드에서 새 계정 토큰 입력

## 6. 수동 실행 / 점검
```bash
python scripts/run_once.py --account demo --dry-run   # AI 호출 없이 프롬프트만 확인
python scripts/run_once.py --account demo             # 글 1개 생성 → 초안
python scripts/run_once.py --account demo --ideas     # 글감 수집
```

## 7. 폴더 구조
```
config.yaml            설정 (AI 백엔드, 게시 시각, 모드, 계정 목록)
.env                   키 (API 키, 쿠팡 키, 앱 시크릿) — 절대 공유 금지
accounts/<id>/         rules.md(말투 규칙) · profile.md(페르소나/사실) · topics.yaml(주제)
app/
  main.py              스케줄러 + 대시보드 기동
  scheduler.py         09/14/20시 슬롯, 토큰 갱신, 글감 수집 잡
  service.py           생성→저장/게시, 한도, 링크, 토큰 관리
  generator.py         주제 선택, 프롬프트, 자가 검수
  ai_backend.py        OpenAI Responses API / 기존 Claude 호환 백엔드
  threads_api.py       Threads 게시·토큰
  facebook_api.py      Facebook 페이지 게시·댓글
  instagram_api.py     Instagram 캐러셀 게시·댓글
  slides_cards.py      Google Slides API 로 카드뉴스 이미지 생성
  coupang.py           파트너스 검색·딥링크 (HMAC)
  trend.py             글감 찾기 (Google 뉴스 RSS → AI 제안)
  store.py             SQLite (data/app.db)
  dashboard/           Flask 대시보드 (카드 이미지는 /media/cards/ 로 서빙)
scripts/               setup_token.md · setup_facebook.md · setup_google_slides.md · register_task.ps1 · run_once.py
data/app.db            초안/게시 이력/토큰 (백업 대상)
data/cards/            생성된 카드뉴스 이미지 (post_id 별 폴더)
logs/app.log           실행 로그
```

## 8. 조회수 파이프라인 (100만 조회 설계)
```
훅 첫 줄 → 공감/실패담 → 구체 숫자 → 댓글 유도 질문  (본문에 링크 없음)
      ↓ 게시 (아침 08:00 / 점심 12:30 / 밤 21:00)
      ↓ 링크는 첫 댓글에 (link_placement: reply)
      ↓ 매일 02:00 조회수·좋아요·댓글 수집 (Threads Insights)
      ↓ 조회수 상위 3개 글을 다음 글 생성 시 예시로 투입 (내 계정 데이터로 학습)
```
- 규칙은 `accounts/<id>/rules.md` 의 "조회수 규칙" 섹션. 반응 없는 훅 패턴은 거기서 빼고, 잘 되는 패턴은 추가.
- 대시보드 글 목록 "조회수" 정렬로 뭐가 터졌는지 확인 → 그 주제를 `topics.yaml` 에 변형해서 여러 개 추가.
- 계정 초반 2주는 링크 없이 공감 글만 (도달 확보) → 이후 링크 댓글 시작.

## 9. 클라우드 서버로 옮기기 (컴퓨터 꺼도 24시간 자동, 인스타그램/토스 API 에도 필요)
**AWS 계정이 아예 없다면** → [scripts/setup_cloud_server.md](scripts/setup_cloud_server.md) 에 계정 생성부터
고정 IP 연결까지 처음부터 정리해뒀습니다. 이미 계정/인스턴스가 있다면 아래 요약만으로 충분:
1. AWS Lightsail 서울 → Ubuntu 24.04, $5(1GB) 인스턴스 생성 → **고정 IP 연결(중요, 재부팅해도 안 바뀌게)** → 네트워킹에서 TCP 5000 허용 → SSH 키(.pem) 다운로드
2. `config.yaml`: `dashboard.host: 0.0.0.0`, `dashboard.password: "강한비밀번호"`, `dashboard.public_base_url: "http://<고정IP>:5000"` (인스타그램 카드뉴스 이미지가 이 주소로 열려야 게시됨)
3. 내 PC PowerShell 에서 (처음 한 번, 서버 설치 포함):
   ```powershell
   .\scripts\deploy.ps1 -Server <서버IP> -Key "$HOME\Downloads\LightsailDefaultKey-ap-northeast-2.pem" -Setup
   ```
4. 서버 `.env`에도 `OPENAI_API_KEY`를 설정하고 서비스를 시작한다 (Claude 로그인 불필요):
   ```powershell
   ssh -i "$HOME\Downloads\LightsailDefaultKey-ap-northeast-2.pem" ubuntu@<서버IP>
   sudo systemctl start threads-auto
   ```
5. **내 PC 의 프로그램은 끄기** (둘 다 켜져 있으면 두 번 게시됨)
6. 이후 설정/주제 바꾼 뒤엔 `.\scripts\deploy.ps1 -Server <IP> -Key "...pem"` 로 다시 올리면 끝
   - 운영 DB와 토큰은 서버에 보존되며 기본 배포에서 덮어쓰지 않습니다.
   - 재해복구 목적으로 로컬 `data/`를 서버에 복원할 때만 `-IncludeData`를 명시하세요.

## 10. 주의 (영상의 실수 3가지 반영)
- **토큰 60일 만료**: 매일 03:30 자동 갱신 시도 + 대시보드 경고. 만료를 넘기면 재발급 필요.
- **규칙 파일 없이 돌리기 금지**: `rules.md` 가 글 퀄리티의 전부. AI 티 나는 글은 계정 노출이 줄어듦.
- **하루 게시 수**: `max_per_day` 기본 3. 5 이상은 계정 정지 위험. Threads API 자체 한도는 24시간 250개.
- 쿠팡 파트너스 고지 문구(`coupang.disclosure`)는 법적 필수. 본문에 넣기 싫으면 프로필 소개글에 반드시 기재.
- **인스타그램은 이미지가 공개 URL 이어야 게시 가능** (공식 API 제약). `dashboard.public_base_url` 미설정 시 인스타그램만 실패로 남고 Threads/Facebook 은 정상 게시됨.
- 페이스북 페이지 액세스 토큰은 대시보드의 "페이스북 페이지 연결" 에서 저장 (사용자 토큰 → 페이지 선택 흐름, [scripts/setup_facebook.md](scripts/setup_facebook.md) 참고). Threads 토큰과 달리 자동 만료 갱신 로직은 없음 — 게시 실패 시 다시 연결.

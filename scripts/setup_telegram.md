# 텔레그램 알림 설정

글이 게시될 때마다(성공/실패, 플랫폼별) 텔레그램으로 메시지를 받습니다.

## 1. 봇 만들기 (텔레그램 앱에서)
1. 텔레그램 앱에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력
3. 봇 이름 입력 (예: `threads-auto-alert`)
4. 봇 아이디(username) 입력 — `bot`으로 끝나야 함 (예: `threads_auto_alert_bot`)
5. 완료되면 **토큰**이 옵니다 (예: `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`) — 이걸 복사해두세요

## 2. 내 채팅 ID 알아내기
1. 방금 만든 봇을 텔레그램에서 검색해서 **대화 시작** (아무 메시지나 하나 보내기, 예: "안녕")
2. 브라우저에서 아래 주소 접속 (`<토큰>` 자리에 1번에서 받은 토큰 입력):
   ```
   https://api.telegram.org/bot<토큰>/getUpdates
   ```
3. 결과 JSON에서 `"chat":{"id":123456789, ...}` 의 숫자를 찾으면 그게 채팅 ID

## 3. 서버에 값 입력
서버(SSH 접속 후)에서:
```bash
cd ~/threads-auto
nano .env
```
아래 두 줄 추가/수정:
```
TELEGRAM_BOT_TOKEN=<1번에서 받은 토큰>
TELEGRAM_CHAT_ID=<2번에서 찾은 숫자>
```
저장(Ctrl+O, Enter) 후 종료(Ctrl+X), 그다음:
```bash
sudo systemctl restart threads-auto
```

## 확인
다음 게시 예정 시각이 되면(또는 대시보드에서 글 보기 > 즉시 게시 테스트) 텔레그램으로 아래 형식의 메시지가 옵니다:
```
✅ 육아템 게시 결과
제목: 밤 11시, 오늘 유일한 내 시간 시작
Threads ✅ · Facebook ✅ · Instagram ❌
```

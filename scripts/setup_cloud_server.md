# 클라우드 서버 처음부터 만들기 (AWS Lightsail)

컴퓨터를 꺼도 24시간 자동으로 게시되게 하려면 클라우드 서버가 필요합니다.
**인스타그램 카드뉴스 게시**와 (나중에) **토스쇼핑 Open API의 IP 등록**에도 고정된 공인 IP가 필요해서
이 프로그램은 클라우드 서버 운영을 전제로 설계돼 있습니다. 월 5~7달러 정도 듭니다.

> ⚠️ **계정 생성/결제 카드 등록은 본인이 직접 해야 합니다.** 아래는 그 단계까지 포함한 처음부터 가이드입니다.
> 이 부분(1~2번)은 제가 대신 클릭할 수 없으니 본인이 진행하고, 막히면 화면을 캡처해서 물어보세요.

## 1. AWS 계정 만들기 (이미 있으면 건너뛰기)
1. https://aws.amazon.com/ko/ → **AWS 계정 생성**
2. 이메일, 이름, 카드 정보 입력 (본인 결제 수단 — 프리티어/최소 결제 확인 단계 있음, $1 정도 임시 승인 후 환불됨)
3. 본인 인증(SMS) 완료 → 요금제는 **Basic (무료)** 선택하면 충분

## 2. Lightsail 인스턴스 만들기
1. https://lightsail.aws.amazon.com/ 접속 (콘솔 로그인 후)
2. **인스턴스 생성** 클릭
3. **리전**: 서울(ap-northeast-2) 선택 (한국 사용자 대상이면 지연시간 유리)
4. **플랫폼**: Linux/Unix → **OS 전용** → **Ubuntu 24.04 LTS**
5. **인스턴스 요금제**: 월 $5(1GB RAM) 플랜이면 충분 (더 여유롭게 하려면 $7 플랜)
6. **SSH 키 페어**: "새 키 페어 생성" (처음이면) → 이름 지정 → **다운로드** 눌러서 `.pem` 파일을 꼭 저장해두기
   (예: `C:\Users\<내계정>\Downloads\LightsailDefaultKey-ap-northeast-2.pem`) — 이 파일이 없으면 서버 접속 불가
7. 인스턴스 이름 아무거나 (예: `threads-auto`) → **인스턴스 생성**
8. 1~2분 기다리면 "실행 중" 상태로 바뀜

## 3. 고정 IP(Static IP) 연결 — 꼭 하세요
기본 IP는 서버를 재부팅하면 바뀔 수 있어서, 인스타그램 이미지 URL/토스 API IP 등록이 깨집니다.
1. Lightsail 콘솔 → **네트워킹** 탭 → **고정 IP 생성**
2. 리전은 인스턴스와 동일하게, **연결할 인스턴스**로 방금 만든 인스턴스 선택 → 생성
3. 발급된 고정 IP 주소를 메모해두세요 (예: `13.125.xx.xx`) — 아래 5번, 그리고 나중에 `config.yaml`의
   `dashboard.public_base_url`, 토스 API IP 등록에 그대로 씁니다.

## 4. 방화벽(네트워킹) 포트 열기
1. 인스턴스 상세 페이지 → **네트워킹** 탭 → **IPv4 방화벽**
2. **규칙 추가**: 애플리케이션 "사용자 지정", 프로토콜 TCP, 포트 `5000` → 저장
   (대시보드에 `dashboard.password` 를 반드시 설정한 상태로만 외부에 노출하세요)

## 5. 서버에 프로젝트 올리기 (내 PC PowerShell 에서)
아래 `<서버IP>` 자리에 3번에서 받은 고정 IP를, `<pem경로>` 에 2번에서 받은 키 파일 경로를 넣습니다.
```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\deploy.ps1 -Server <서버IP> -Key "<pem경로>" -Setup
```
- 처음엔 SSH 접속 확인 메시지가 뜨면 `yes` (자동으로 accept-new 처리되어 있어 보통 안 뜸)
- 5분 정도 걸립니다 (Python/Node/Claude Code 설치 + 의존성 설치 + systemd 서비스 등록)

## 6. 서버에서 Claude Code 로그인 (구독 그대로 사용, 한 번만)
```powershell
ssh -i "<pem경로>" ubuntu@<서버IP>
```
접속되면 서버 안에서:
```bash
cd threads-auto
claude
```
URL이 나오면 그 주소를 로컬 PC 브라우저에서 열어 로그인 → 인증 코드를 복사해 터미널에 붙여넣기 → 완료되면 `/exit` 또는 `Ctrl+C`

## 7. 서비스 시작 + 설정 반영
서버 안에서 계속:
```bash
sudo systemctl start threads-auto
sudo systemctl status threads-auto --no-pager
```
"active (running)" 이면 성공. 브라우저에서 `http://<서버IP>:5000` 열어서 대시보드 확인 (아이디 admin, 비밀번호는 `config.yaml`의 `dashboard.password`).

## 8. 인스타그램/토스를 위한 설정값 채우기 (내 PC에서)
1. `config.yaml` 의 `dashboard.public_base_url` 에 `http://<서버IP>:5000` 입력
2. (토스 API 승인 후) 토스 쉐어링크 어드민에 이 고정 IP(`<서버IP>`)를 출발지 IP로 등록
3. 변경사항 반영: 다시 배포
   ```powershell
   .\scripts\deploy.ps1 -Server <서버IP> -Key "<pem경로>"
   ```
   (`-Setup` 없이 실행하면 파일만 갱신하고 서비스 재시작만 함 — 이후 설정/주제/코드 바뀔 때마다 이 명령 반복)

## 9. 마지막 — 내 PC 프로그램은 끄기
로컬 PC와 서버 둘 다 켜져 있으면 게시가 두 번 됩니다. `start.bat` 로 켠 창이 있으면 닫으세요.

## 자주 나는 오류
| 증상 | 원인 / 해결 |
|---|---|
| `Permission denied (publickey)` | pem 키 경로가 틀렸거나, `icacls` 권한 정리가 안 됨 (deploy.ps1 이 자동으로 처리하지만 안 되면 수동으로 `icacls <pem경로> /inheritance:r /grant:r "%USERNAME%:R"`) |
| 대시보드가 안 열림 | 4번 방화벽 규칙(5000번 포트)이 안 열려 있거나, `dashboard.host` 가 `0.0.0.0` 인지 확인 |
| `systemctl status` 가 실패 상태 | `journalctl -u threads-auto -n 50 --no-pager` 로 에러 로그 확인, 보통 `.env`/`config.yaml` 오타 |
| 재부팅 후 대시보드 주소가 안 열림 | 고정 IP(3번)를 안 붙였을 가능성 — 일반 IP는 재부팅 시 바뀜 |

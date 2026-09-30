"""글 생성 AI 백엔드.

- HeadlessClaude : 설치된 Claude Code 를 `claude -p` 로 실행 (구독 사용, 추가 비용 없음)
- AnthropicAPI   : Anthropic Python SDK (ANTHROPIC_API_KEY, 종량제)
- OpenAIAPI      : OpenAI Responses API (OPENAI_API_KEY, 종량제)

둘 다 `generate(system, user) -> str` 인터페이스.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import requests

from app.config import cfg, env


class AIError(RuntimeError):
    pass


class HeadlessClaude:
    def __init__(self, model: str = "", timeout: int = 240):
        self.model = model
        self.timeout = timeout
        # Windows 에서는 npm 이 claude.cmd 셔틀을 만들어 두므로 which 로 찾으면 실행 가능
        self.exe = shutil.which("claude")
        if not self.exe:
            raise AIError("claude 명령을 찾을 수 없습니다. `npm install -g @anthropic-ai/claude-code` 후 다시 시도하세요.")

    def generate(self, system: str, user: str) -> str:
        cmd = [
            self.exe, "-p",
            "--output-format", "json",
            "--tools", "",                 # 도구 사용 금지: 순수 텍스트 생성만
            "--no-session-persistence",
            "--system-prompt", system,
        ]
        if self.model:
            cmd += ["--model", self.model]
        try:
            r = subprocess.run(
                cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout, shell=False,
            )
        except subprocess.TimeoutExpired:
            raise AIError(f"claude 응답 시간 초과 ({self.timeout}s)")
        if r.returncode != 0:
            raise AIError(f"claude 실행 실패 (code {r.returncode}): {(r.stderr or r.stdout)[:500]}")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise AIError(f"claude 출력 파싱 실패: {r.stdout[:300]}")
        if data.get("is_error"):
            raise AIError(f"claude 오류: {str(data.get('result'))[:300]}")
        text = data.get("result") or ""
        if not text.strip():
            raise AIError("claude 가 빈 응답을 반환했습니다.")
        return text.strip()


class AnthropicAPI:
    def __init__(self, model: str = "claude-opus-5", timeout: int = 240):
        try:
            import anthropic
        except ImportError:
            raise AIError("anthropic 패키지가 없습니다. `pip install anthropic`")
        if not env("ANTHROPIC_API_KEY"):
            raise AIError(".env 에 ANTHROPIC_API_KEY 가 없습니다.")
        self.client = anthropic.Anthropic(timeout=float(timeout))
        self.model = model

    def generate(self, system: str, user: str) -> str:
        import anthropic
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.RateLimitError as e:
            raise AIError(f"API 요청 한도 초과: {e}")
        except anthropic.APIStatusError as e:
            raise AIError(f"API 오류 {e.status_code}: {e.message}")
        except anthropic.APIConnectionError as e:
            raise AIError(f"API 연결 실패: {e}")
        if resp.stop_reason == "refusal":
            raise AIError("모델이 응답을 거부했습니다. 주제/규칙을 확인하세요.")
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            raise AIError("API 가 빈 응답을 반환했습니다.")
        return text


class OpenAIAPI:
    """OpenAI Responses API로 텍스트 생성. 키와 응답 오류 원문은 로그에 남기지 않는다."""

    def __init__(self, model: str = "gpt-5-mini", timeout: int = 120):
        self.key = env("OPENAI_API_KEY").strip()
        if not self.key:
            raise AIError(".env 에 OPENAI_API_KEY 가 없습니다.")
        if not self.key.startswith("sk-") or not self.key.isascii():
            raise AIError("OPENAI_API_KEY 형식을 확인해주세요.")
        self.model = model
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "instructions": system,
            "input": user,
            "max_output_tokens": 2048,
            "store": False,
        }
        if self.model.startswith("gpt-5"):
            payload["reasoning"] = {"effort": "low"}
        try:
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.key}"},
                json=payload, timeout=self.timeout,
            )
        except requests.Timeout:
            raise AIError(f"OpenAI 응답 시간 초과 ({self.timeout}s)") from None
        except requests.RequestException:
            raise AIError("OpenAI 연결 실패") from None
        if response.status_code != 200:
            reasons = {
                400: "요청 또는 모델 설정 확인 필요",
                401: "API 키 인증 실패",
                403: "API 키 또는 모델 접근 권한 확인 필요",
                429: "API 잔액 또는 요청 한도 확인 필요",
            }
            raise AIError(f"OpenAI 오류 {response.status_code}: "
                          f"{reasons.get(response.status_code, '서비스 요청 실패')}")
        try:
            data = response.json()
        except ValueError:
            raise AIError("OpenAI 응답 파싱 실패") from None
        if data.get("status") != "completed":
            raise AIError("OpenAI 생성 미완료 — 예비 생성 사용")
        text = "".join(
            content.get("text", "")
            for item in data.get("output", []) if item.get("type") == "message"
            for content in item.get("content", []) if content.get("type") == "output_text"
        ).strip()
        if not text:
            raise AIError("OpenAI 가 빈 응답을 반환했습니다.")
        return text


def get_backend():
    ai = cfg["ai"]
    backend = ai.get("backend", "headless")
    timeout = int(ai.get("timeout_sec", 240))
    if backend == "fallback":
        raise AIError("외부 AI 사용 안 함 — 내장 예비 생성 사용")
    if backend == "openai":
        return OpenAIAPI(model=ai.get("model", "gpt-5-mini"), timeout=timeout)
    if backend == "api":
        return AnthropicAPI(model=ai.get("model", "claude-opus-5"), timeout=timeout)
    if backend == "headless":
        return HeadlessClaude(model=ai.get("headless_model", "") or "", timeout=timeout)
    raise AIError("지원하지 않는 AI backend 설정입니다.")

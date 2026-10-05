from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# 안전 분류기가 요청을 거절하면 서버가 알아서 다른 모델로 이어서 처리한다
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    pass


class LLM:
    """Claude 호출 래퍼. 인증 정보가 없으면 available=False 로 두고 호출부에서 기능을 건너뛴다."""

    def __init__(self, model: str, log=print):
        self.model = model
        self.log = log
        self.client: anthropic.Anthropic | None = None
        try:
            self.client = anthropic.Anthropic(max_retries=4)
        except Exception as e:  # 인증 수단을 전혀 못 찾은 경우
            log(f"[Claude] 클라이언트를 만들 수 없습니다: {e}")
        self.available = self.client is not None and _has_credentials()
        if not self.available:
            log("[Claude] API 키가 없어 AI 기능(필러 판단·일러스트·개인정보 판단)은 규칙 기반으로만 동작합니다. "
                ".env 에 ANTHROPIC_API_KEY 를 넣어주세요.")

    def _common(self, effort: str) -> dict:
        return dict(
            model=self.model,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": effort},
        )

    def _check(self, response) -> None:
        if response.stop_reason == "refusal":
            raise LLMUnavailable("Claude가 요청을 처리하지 않았습니다 (refusal).")
        if response.stop_reason == "max_tokens":
            raise LLMUnavailable("응답이 max_tokens 에서 잘렸습니다.")

    def parse(self, system: str, content, schema: type[T], effort: str = "medium", max_tokens: int = 32000) -> T:
        """구조화된 JSON 응답을 pydantic 모델로 받는다."""
        if not self.available:
            raise LLMUnavailable("Claude 인증 정보 없음")
        try:
            with self.client.beta.messages.stream(
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                **self._common(effort),
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            self.available = False
            raise LLMUnavailable(f"API 키 인증 실패: {e}") from e
        self._check(response)
        return response.parsed_output

    def text(self, system: str, content, effort: str = "medium", max_tokens: int = 32000) -> str:
        if not self.available:
            raise LLMUnavailable("Claude 인증 정보 없음")
        try:
            with self.client.beta.messages.stream(
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                **self._common(effort),
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            self.available = False
            raise LLMUnavailable(f"API 키 인증 실패: {e}") from e
        self._check(response)
        return "".join(b.text for b in response.content if b.type == "text")


def _has_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # `ant auth login` 으로 저장된 프로필
    return (Path.home() / ".config" / "anthropic").exists()


def image_block(png_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png_bytes).decode()},
    }

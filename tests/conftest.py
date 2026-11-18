"""테스트 공용 도구. 실제 Claude 를 부르지 않도록 가짜 LLM 을 쓴다."""
from __future__ import annotations

import pytest

from autoedit.llm import LLMUnavailable
from autoedit.transcribe import Word


class FakeLLM:
    """llm.LLM 대신 쓰는 가짜. parse() 가 미리 정해둔 응답(또는 예외)을 돌려준다."""

    def __init__(self, response=None, error: Exception | None = None):
        self.available = True
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, content, schema, effort="medium", max_tokens=32000):
        self.calls.append((system, content))
        if self.error:
            raise self.error
        return schema.model_validate(self.response)


def words_from(spec: str, step: float = 0.5, dur: float = 0.4) -> list[Word]:
    """"안녕 어 하세요" → 0.5초 간격으로 놓인 단어 목록."""
    return [Word(round(i * step, 3), round(i * step + dur, 3), t) for i, t in enumerate(spec.split())]


@pytest.fixture
def fake_llm():
    return FakeLLM


@pytest.fixture
def unavailable():
    return LLMUnavailable("테스트용 실패")

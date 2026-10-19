import pytest

from autoedit.privacy import detect_spoken_pii, regex_pii
from autoedit.transcribe import Word

from conftest import FakeLLM


@pytest.mark.parametrize("text, kind", [
    ("010-1234-5678", "전화번호"),
    ("010 1234 5678", "전화번호"),
    ("02)123-4567", "전화번호"),
    ("O1O-1234-5678", "전화번호"),       # OCR 이 0 을 O 로 읽은 경우
    ("900101-1234567", "주민등록번호"),
    ("900101-1******", "주민등록번호"),
    ("abc.def@example.co.kr", "이메일"),
    ("1234-5678-9012-3456", "카드번호"),
    ("12가 3456", "차량번호"),
    ("서울시 강남구 테헤란로 123", "주소"),
    ("110-123-456789", "계좌번호"),
])
def test_regex_pii_detects(text, kind):
    assert regex_pii(text) == kind


@pytest.mark.parametrize("text", [
    "2026-10-05",          # 날짜는 계좌번호가 아니다
    "12-34-56",            # 숫자가 너무 짧음
    "복리와 단리의 차이",
    "가격은 15000원",
])
def test_regex_pii_ignores(text):
    assert regex_pii(text) is None


def _w(spec):
    return [Word(i * 0.5, i * 0.5 + 0.4, t) for i, t in enumerate(spec.split())]


def test_spoken_phone_number_starts_at_digits():
    words = _w("제 번호는 010 1234 5678 입니다")
    beeps = detect_spoken_pii(words, None, [], log=lambda *_: None)
    assert len(beeps) == 1
    b = beeps[0]
    assert b.kind == "전화번호"
    assert b.start == pytest.approx(words[2].start - 0.05)  # "번호는" 은 덮지 않는다
    assert b.end == pytest.approx(words[4].end + 0.05)


def test_spoken_pii_llm_and_allowlist():
    words = _w("저는 홍길동 이고 친구는 김철수 입니다")
    llm = FakeLLM({"items": [{"first_index": 1, "last_index": 1, "kind": "실명"},
                             {"first_index": 4, "last_index": 4, "kind": "실명"},
                             {"first_index": 0, "last_index": 99, "kind": "범위 밖"}]})
    beeps = detect_spoken_pii(words, llm, ["홍길동"], log=lambda *_: None)
    assert [b.text for b in beeps] == ["김철수"]


def test_spoken_pii_llm_failure_keeps_regex(unavailable):
    words = _w("번호 010 1234 5678")
    beeps = detect_spoken_pii(words, FakeLLM(error=unavailable), [], log=lambda *_: None)
    assert len(beeps) == 1

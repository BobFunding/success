"""할 말 자동 생성 (AI 없이, DESIGN.md 4절): 동작별 문장 틀 + 대상 글자, 받침에 맞는 조사.

말투: 차분(기본, 1편) / 친근 / 전문. 사람은 확인 단계에서 문장만 다듬으면 된다."""
from __future__ import annotations

import re

COUNT = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"]
_DIGIT_BATCHIM = set("013678")          # 영 일 삼 육 칠 팔 → 받침 있음
_LATIN_BATCHIM = set("lmnrLMNR")        # 엘 엠 엔 알


def count_word(n: int) -> str:
    """3 → '세' (세 단계)."""
    return COUNT[n] if 0 < n < len(COUNT) else str(n)


def has_batchim(word: str) -> bool | None:
    """마지막 글자에 받침이 있는지. 모르면 None."""
    w = re.sub(r"[\s\)\]\}\"'’”.,!?·]+$", "", word)
    if not w:
        return None
    c = w[-1]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    if c.isdigit():
        return c in _DIGIT_BATCHIM
    if c.isalpha():
        return c in _LATIN_BATCHIM
    return None


def _rieul(word: str) -> bool:
    c = re.sub(r"[\s\)\]\}\"'’”.,!?·]+$", "", word)[-1:]
    return bool(c) and "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 == 8


def josa(word: str, pair: str) -> str:
    """word + 알맞은 조사. pair: '을/를', '은/는', '이/가', '과/와', '으로/로'."""
    a, b = pair.split("/")
    bat = has_batchim(word)
    if pair == "으로/로":
        return word + (b if bat is False or _rieul(word) else a if bat else "(으)로")
    if bat is None:
        return f"{word}{a}({b})" if len(a) == 1 else word + b
    return word + (a if bat else b)


# 말투별 문장 틀. {대상}, {버튼} 에 조사를 붙인 말이 들어간다.
TEMPLATES = {
    "차분": {
        "클릭": "{대상_버튼} 눌러 주세요.",
        "링크": "{대상_을} 눌러 주세요.",
        "입력": "{대상_을} 적어 주세요.",
        "입력+버튼": "{대상_을} 적고, {버튼_을} 눌러 주세요.",
        "체크": "{대상_에} 체크해 주세요.",
        "선택": "{대상_은} 목록에서 골라 주세요.",
        "스크롤": "아래로 내려 볼게요.",
        "보여주기": "{대상_을} 확인해 주세요.",
        "대기": "잠시 기다려 주세요.",
        "마지막클릭": "{대상_버튼} 누르면 끝이에요.",
    },
    "친근": {
        "클릭": "{대상_버튼} 눌러 볼까요?",
        "링크": "{대상_을} 눌러 볼까요?",
        "입력": "{대상_을} 적어 볼게요.",
        "입력+버튼": "{대상_을} 적고, {버튼_을} 눌러요.",
        "체크": "{대상_에} 체크해 볼게요.",
        "선택": "{대상_은} 목록에서 고르면 돼요.",
        "스크롤": "아래로 쭉 내려 볼게요.",
        "보여주기": "{대상_을} 한번 볼까요?",
        "대기": "잠깐만 기다려요.",
        "마지막클릭": "{대상_버튼} 누르면 끝!",
    },
    "전문": {
        "클릭": "{대상_버튼} 누릅니다.",
        "링크": "{대상_을} 누릅니다.",
        "입력": "{대상_을} 입력합니다.",
        "입력+버튼": "{대상_을} 입력하고 {버튼_을} 누릅니다.",
        "체크": "{대상_에} 체크합니다.",
        "선택": "{대상_은} 목록에서 선택합니다.",
        "스크롤": "아래로 이동합니다.",
        "보여주기": "{대상_을} 확인합니다.",
        "대기": "잠시 기다립니다.",
        "마지막클릭": "{대상_버튼} 누르면 완료됩니다.",
    },
}


def _fill(tpl: str, target: str, button: str = "") -> str:
    t = target.strip() or "이것"
    btn_word = t if t.endswith("버튼") else f"{t} 버튼"
    return tpl.format(대상_을=josa(t, "을/를"), 대상_은=josa(t, "은/는"), 대상_에=f"{t}에",
                      대상_버튼=josa(btn_word, "을/를"), 버튼_을=josa(button.strip() or "버튼", "을/를"))


def scene_line(action: str, target: str, *, button: str = "", kind: str = "", first: bool = False,
               last: bool = False, tone: str = "차분") -> str:
    """장면 하나의 할 말. kind='링크' 면 '버튼' 을 붙이지 않는다."""
    T = TEMPLATES.get(tone, TEMPLATES["차분"])
    key = action
    if action == "입력" and button:
        key = "입력+버튼"
    elif action == "클릭" and kind == "링크":
        key = "링크"
    if last and action == "클릭":
        key = "마지막클릭" if kind != "링크" else key
    s = _fill(T[key], target, button)
    if first:
        s = "먼저, " + s
    elif last:
        s = "마지막으로, " + s
    return s


def topic_words(topic: str) -> str:
    """'관장님 회원가입 방법' → '관장님 회원가입' (문장에 '방법을' 이 다시 붙으므로)."""
    return re.sub(r"\s*(하는\s*)?방법\s*$", "", topic.strip())


def intro_outro(topic: str, n_steps: int, brand_spoken: str, next_topic: str = "") -> tuple[list[str], list[str]]:
    """인트로 2문장, 아웃트로 2문장 (RULES.md 2절 공통 틀)."""
    t = topic_words(topic)
    hello = f"안녕하세요, {brand_spoken}입니다." if brand_spoken else "안녕하세요."
    intro = [hello, f"오늘은 {t} 방법을, {count_word(n_steps)} 단계로 알려 드릴게요."]
    bye = f"{brand_spoken}였습니다." if brand_spoken and not has_batchim(brand_spoken) else \
          (f"{brand_spoken}이었습니다." if brand_spoken else "고맙습니다.")
    nxt = f"다음 영상에서는 {topic_words(next_topic)} 방법을 알려 드릴게요. " if next_topic else ""
    outro = [f"오늘 배운 {count_word(n_steps)} 단계, 기억하시죠?", nxt + bye]
    return intro, outro


def title(topic: str, n_steps: int) -> str:
    return f"{topic_words(topic)}, [{n_steps}단계]면 끝!"

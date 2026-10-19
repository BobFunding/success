"""번역 자막: 외국어로 말한 문장을 한국어(등)로 옮겨 화면에 크게 띄운다. 원문은 그 아래 작게.

결과는 작업 폴더의 translations.json (컷 편집본 시간 기준)에 저장해서 사람이 고칠 수 있게 하고,
최종 렌더링(render_from_plan)은 이 파일만 보고 자막을 그린다.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .llm import LLM, LLMUnavailable

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")


class SentenceTranslation(BaseModel):
    index: int = Field(description="문장 번호")
    text: str = Field(description="번역문. 자막으로 읽기 좋게 짧고 자연스러운 구어체")


class TranslationList(BaseModel):
    items: list[SentenceTranslation]


TRANSLATE_SYSTEM = """유튜브 영상의 자막 번역가입니다. 번호가 붙은 문장(받아쓰기 결과)을 {target} 자막으로 옮깁니다.
- 말하는 사람의 말투를 살린 자연스러운 구어체로, 자막으로 1~2초 안에 읽히게 짧게 씁니다.
- 앞뒤 문장을 참고해서 끊긴 문장도 뜻이 통하게 옮기세요.
- "(삐-)" 는 가린 개인정보입니다. 번역문에도 "(삐-)" 그대로 두고, 무엇이었는지 추측하지 마세요.
- 받아쓰기 오류로 보이는 단어는 문맥에 맞게 해석하되, 없는 내용을 지어내지 마세요."""

LANG_NAMES = {"ko": "한국어", "en": "영어", "ja": "일본어"}


def needs_translation(text: str, target: str) -> bool:
    """이미 목표 언어인 문장은 번역하지 않는다 (한국어 ↔ 라틴 문자 기준의 단순 판정)."""
    hangul, latin = len(_HANGUL.findall(text)), len(_LATIN.findall(text))
    if target == "ko":
        return latin > hangul
    return hangul > latin


def translate_sentences(sentences: list[dict], target: str, llm: LLM | None, log=print) -> list[dict]:
    """sentences: group_sentences 결과 (개인정보를 가린 대본으로 만든 것이어야 한다).
    돌려주는 값: [{"start", "end", "text"}] — 번역이 필요한 문장만."""
    todo = [i for i, s in enumerate(sentences) if needs_translation(s["text"], target)]
    if not todo:
        return []
    if llm is None or not llm.available:
        log("[번역] Claude API 키가 없어 번역 자막을 건너뜁니다. translations.json 을 직접 만들어도 됩니다.")
        return []
    listing = "\n".join(f"{i}: {s['text']}" + ("" if i in todo else "  (번역 불필요, 문맥 참고용)")
                        for i, s in enumerate(sentences))
    try:
        result = llm.parse(TRANSLATE_SYSTEM.format(target=LANG_NAMES.get(target, target)), listing,
                           TranslationList, effort="medium")
    except LLMUnavailable as e:
        log(f"[번역] Claude 번역 실패, 번역 자막 없이 진행: {e}")
        return []
    wanted = set(todo)
    out = [{"start": sentences[t.index]["start"], "end": sentences[t.index]["end"], "text": t.text.strip()}
           for t in result.items if t.index in wanted and t.text.strip()]
    log(f"[번역] {LANG_NAMES.get(target, target)} 번역 자막 {len(out)}개")
    return sorted(out, key=lambda x: x["start"])

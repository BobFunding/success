"""받아쓰기 교정: 발음 때문에 잘못 받아 적은 단어를 Claude가 주제 용어와 문맥을 보고 고친다.

Whisper 의 hotwords / initial_prompt 로는 발음이 바뀌는 단어("단리"→[달리])를 바로잡지 못한다.
단어 하나를 단어 하나로만 바꾸므로 단어 수와 타임스탬프는 그대로 유지된다
(컷 계산, 개인정보 구간, 자막 시간이 모두 단어 타임스탬프에 기대고 있기 때문).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .cutter import STRONG_FILLER, normalize
from .llm import LLM, LLMUnavailable
from .transcribe import Word


class WordFix(BaseModel):
    index: int = Field(description="고칠 단어의 번호")
    text: str = Field(description="고친 단어. 조사·어미·문장부호는 원래 단어와 같게 유지")
    reason: str = Field(description="짧은 이유 (예: 주제 용어 '단리'의 발음 오인식)")


class TranscriptFixes(BaseModel):
    fixes: list[WordFix]


CORRECT_SYSTEM = """당신은 한국어 유튜브 영상의 받아쓰기 교정자입니다.
번호가 붙은 단어 목록은 음성 인식(Whisper) 결과입니다. 소리는 비슷하지만 잘못 받아 적은 단어만 고칩니다.

고칠 것:
- 발음 변화 때문에 잘못 적힌 주제 용어: 예) 주제가 "단리"인데 "달리는" → "단리는" (단리는 실제 발음이 [달리])
- 문맥상 명백히 틀린 동음/유사음 단어: 예) 금융 이야기 중 "이자을" → "이자를"

지킬 것:
- 단어 하나는 단어 하나로만 바꿉니다. 단어를 합치거나 나누거나 지우지 마세요. 고친 단어에 공백을 넣지 마세요.
- 조사·어미·문장부호는 원래 단어의 것을 그대로 둡니다.
- 말버릇("어", "음")과 말더듬은 고치지 않습니다. 자르는 것은 다른 단계가 합니다.
- 숫자, 이름, 연락처는 바꾸지 않습니다.
- 확신이 없으면 고치지 않습니다. 맞는 단어를 바꾸면 자막이 틀어집니다. 고칠 것이 없으면 빈 목록."""


def _acceptable(old: str, new: str) -> bool:
    """단어 하나 → 단어 하나 교정만 받는다. 이상한 응답이 대본을 망가뜨리지 않게 한 번 더 거른다."""
    if not new or new == old or re.search(r"\s", new):
        return False
    if STRONG_FILLER.match(normalize(old)):  # 말버릇은 컷 단계가 판단한다
        return False
    # 숫자가 사라지거나 바뀌면 개인정보(전화번호 등) 감지가 놓칠 수 있다 → 숫자는 손대지 않는다
    if re.sub(r"\D", "", old) != re.sub(r"\D", "", new):
        return False
    # 소리가 비슷한 단어끼리의 교정이므로 길이가 크게 달라지면 의심스럽다
    a, b = normalize(old), normalize(new)
    return bool(b) and abs(len(a) - len(b)) <= max(2, len(a) // 2)


def correct_transcript(words: list[Word], vocabulary: list[str], llm: LLM | None,
                       log=print) -> tuple[list[Word], list[dict]]:
    """교정된 단어 목록과 교정 내역(번호, 원래, 교정, 이유)을 돌려준다. Claude가 없으면 그대로 돌려준다."""
    if not words or llm is None or not llm.available:
        return words, []

    terms = f"이 영상의 주제 용어: {', '.join(vocabulary)}\n\n" if vocabulary else ""
    out = list(words)
    fixes: list[dict] = []
    chunk = 700
    for start in range(0, len(words), chunk):
        end = min(len(words), start + chunk)
        ctx_start, ctx_end = max(0, start - 20), min(len(words), end + 20)
        lines = "\n".join(f"{i}: {words[i].text}" for i in range(ctx_start, ctx_end))
        prompt = (f"{terms}단어 {start}~{end - 1} 번 중에서 잘못 받아 적은 단어를 고쳐주세요 "
                  f"(앞뒤 번호는 문맥 참고용).\n\n{lines}")
        try:
            result = llm.parse(CORRECT_SYSTEM, prompt, TranscriptFixes, effort="medium")
        except LLMUnavailable as e:
            log(f"[교정] Claude 받아쓰기 교정 실패, 원래 대본으로 진행: {e}")
            return words, []
        for f in result.fixes:
            if not (start <= f.index < end):
                continue
            old, new = words[f.index].text, f.text.strip()
            if not _acceptable(old, new):
                continue
            w = words[f.index]
            out[f.index] = Word(w.start, w.end, new, w.prob)
            fixes.append({"index": f.index, "start": w.start, "before": old, "after": new, "reason": f.reason})
    log(f"[교정] 받아쓰기 교정 {len(fixes)}개")
    return out, fixes

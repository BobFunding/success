from autoedit.correct import correct_transcript
from autoedit.transcribe import Word

from conftest import FakeLLM, words_from


def _fix(index, text):
    return {"index": index, "text": text, "reason": "테스트"}


def test_no_llm_returns_words_unchanged():
    words = words_from("달리는 원금에만 이자가 붙어요")
    out, fixes = correct_transcript(words, ["단리"], None, log=lambda *_: None)
    assert out is words and fixes == []


def test_fix_keeps_word_count_and_timestamps():
    words = words_from("오늘은 복리와 달리를 비교합니다")
    llm = FakeLLM({"fixes": [_fix(2, "단리를")]})
    out, fixes = correct_transcript(words, ["복리", "단리"], llm, log=lambda *_: None)
    assert [w.text for w in out] == ["오늘은", "복리와", "단리를", "비교합니다"]
    assert [(w.start, w.end) for w in out] == [(w.start, w.end) for w in words]
    assert fixes == [{"index": 2, "start": words[2].start, "before": "달리를", "after": "단리를", "reason": "테스트"}]
    assert words[2].text == "달리를"  # 원래 목록은 건드리지 않는다
    assert "주제 용어: 복리, 단리" in llm.calls[0][1]


def test_rejects_unsafe_fixes():
    words = words_from("어 번호는 010 달리는 이자")
    llm = FakeLLM({"fixes": [
        _fix(0, "아"),            # 말버릇은 컷 단계 몫
        _fix(2, "공일공"),        # 숫자가 사라지면 개인정보 감지가 놓친다
        _fix(3, "단리 는"),       # 단어를 나누면 안 된다
        _fix(4, "이자에대한설명입니다"),  # 길이가 크게 바뀌면 의심스럽다
        _fix(1, "번호는"),        # 바뀐 게 없음
        _fix(42, "범위밖"),
    ]})
    out, fixes = correct_transcript(words, [], llm, log=lambda *_: None)
    assert [w.text for w in out] == [w.text for w in words]
    assert fixes == []


def test_llm_failure_returns_original(unavailable):
    words = words_from("달리는 이자")
    out, fixes = correct_transcript(words, ["단리"], FakeLLM(error=unavailable), log=lambda *_: None)
    assert out is words and fixes == []


def test_long_transcript_is_chunked():
    words = [Word(i * 0.5, i * 0.5 + 0.4, "달리는" if i == 750 else "말") for i in range(800)]
    llm = FakeLLM({"fixes": [_fix(750, "단리는")]})
    out, fixes = correct_transcript(words, ["단리"], llm, log=lambda *_: None)
    assert len(llm.calls) == 2
    # 같은 응답이 두 번 오지만 750 번은 두 번째 묶음(700~799) 안에서만 반영된다
    assert [f["index"] for f in fixes] == [750]
    assert out[750].text == "단리는"

from autoedit.translate import needs_translation, translate_sentences

from conftest import FakeLLM


def test_needs_translation():
    assert needs_translation("I like Korean style.", "ko")
    assert not needs_translation("한국 남자 특징", "ko")
    assert needs_translation("한국 남자 특징", "en")


def test_translate_only_foreign_sentences():
    sents = [{"start": 0, "end": 1, "text": "안녕하세요"}, {"start": 1, "end": 2, "text": "Nice to meet you."}]
    llm = FakeLLM({"items": [{"index": 0, "text": "잘못된 번역"}, {"index": 1, "text": "반가워요."}]})
    out = translate_sentences(sents, "ko", llm, log=lambda *_: None)
    assert out == [{"start": 1, "end": 2, "text": "반가워요."}]
    assert "문맥 참고용" in llm.calls[0][1]


def test_translate_without_llm_or_on_failure(unavailable):
    sents = [{"start": 0, "end": 1, "text": "Hello"}]
    assert translate_sentences(sents, "ko", None, log=lambda *_: None) == []
    assert translate_sentences(sents, "ko", FakeLLM(error=unavailable), log=lambda *_: None) == []

import pytest

from autoedit.pipeline import _mask, subtitle_cues, write_srt
from autoedit.transcribe import Word, group_sentences

from conftest import words_from


def test_group_sentences_split_on_gap_and_punctuation():
    words = [Word(0.0, 0.4, "안녕하세요."), Word(0.5, 0.9, "오늘은"), Word(1.0, 1.4, "복리"),
             Word(3.0, 3.4, "시작합니다")]
    sents = group_sentences(words)
    assert [s["text"] for s in sents] == ["안녕하세요.", "오늘은 복리", "시작합니다"]
    assert sents[1]["word_range"] == [1, 2]
    assert sents[1]["start"] == 0.5 and sents[1]["end"] == 1.4


def test_cues_hide_beeped_words_and_merge():
    words = words_from("제 번호는 010 1234 5678 입니다")
    beeps = [{"start": 0.95, "end": 2.45}]
    cues = subtitle_cues(words, beeps)
    text = " ".join(c[2] for c in cues)
    assert "010" not in text and "1234" not in text and "5678" not in text
    assert text.count("(삐-)") == 1
    hidden = next(c for c in cues if "(삐-)" in c[2])
    assert hidden[1] >= 2.4  # 삐- 소리가 나는 동안 자막이 유지된다


def test_cues_split_long_sentence_evenly():
    words = words_from("복리는 이자에 이자가 붙는 방식이고 단리는 원금에만 이자가 붙는 방식입니다")
    cues = subtitle_cues(words, [], max_chars=22)
    assert len(cues) >= 2
    lengths = [len(c[2]) for c in cues]
    assert max(lengths) - min(lengths) <= 12  # 마지막 조각만 짧게 남지 않는다
    assert " ".join(c[2] for c in cues) == " ".join(w.text for w in words)


def test_short_cue_is_extended_but_not_over_next():
    words = [Word(0.0, 0.2, "네."), Word(0.5, 0.9, "다음")]
    cues = subtitle_cues(words, [], min_show=0.8)
    assert cues[0][1] == pytest.approx(0.5)  # 다음 자막 시작까지만 늘린다
    assert cues[1][1] == pytest.approx(1.3)


def test_write_srt_format(tmp_path):
    path = tmp_path / "s.srt"
    write_srt([Word(61.5, 62.25, "안녕.")], [], path)
    assert path.read_text(encoding="utf-8").splitlines()[:3] == ["1", "00:01:01,500 --> 00:01:02,300", "안녕."]


@pytest.mark.parametrize("text, expected", [
    ("", ""),
    ("가", "가*"),
    ("홍길동", "홍*동"),
    ("010-1234-5678", "010*******678"),
])
def test_mask(text, expected):
    assert _mask(text) == expected


def test_write_ass_with_translation(tmp_path):
    from autoedit.pipeline import write_ass
    words = [Word(0.0, 0.8, "안녕하세요."), Word(2.0, 2.5, "I"), Word(2.5, 3.0, "like"), Word(3.0, 3.6, "it.")]
    tr = [{"start": 2.0, "end": 3.6, "text": "좋아요."}]
    path = tmp_path / "s.ass"
    write_ass(words, [], path, 3840, 2160, "Pretendard", 0.055, tr)
    events = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")]
    assert any(",Main,," in l and "안녕하세요." in l for l in events)    # 번역 불필요 → 크게
    assert any(",Default,," in l and "I like it." in l for l in events)  # 원문 → 작게
    assert any(",Trans,," in l and "좋아요." in l for l in events)
    assert "PlayResX: 3840" in path.read_text(encoding="utf-8")


def test_masked_words_hide_beeps_for_translation():
    from autoedit.pipeline import masked_words
    words = words_from("call me at 010 1234 5678 okay")
    shown = masked_words(words, [{"start": 1.45, "end": 2.95}])
    assert [w.text for w in shown] == ["call", "me", "at", "(삐-)", "okay"]

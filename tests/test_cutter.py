import wave

import numpy as np
import pytest

from autoedit.cutter import (TimeMap, compute_keep_segments, decide_fillers, detect_silences, normalize,
                             snap_to_frames)
from autoedit.transcribe import Word

from conftest import FakeLLM, words_from


def test_normalize_removes_punctuation_and_spaces():
    assert normalize(" 어, ") == "어"
    assert normalize("음...") == "음"
    assert normalize("“그래서”!") == "그래서"


# ───────────── 필러 판정 ─────────────

def test_strong_fillers_cut_without_llm():
    words = words_from("오늘은 어 복리를 음... 설명 그 드릴게요")
    cuts = decide_fillers(words, None, log=lambda *_: None)
    assert set(cuts) == {1, 3}  # "그" 는 애매한 후보라 규칙만으로는 남긴다


def test_english_fillers_cut():
    words = words_from("Um, I like uh Korean style hmm... umbrella")
    cuts = decide_fillers(words, None, log=lambda *_: None)
    assert set(cuts) == {0, 3, 6}  # umbrella 는 필러가 아님


def test_long_filler_is_kept():
    # 2초 넘게 늘어진 "음" 은 생각하는 시간일 수 있어 자르지 않는다
    words = [Word(0.0, 0.4, "네"), Word(0.5, 3.0, "음"), Word(3.1, 3.5, "좋아요")]
    assert decide_fillers(words, None, log=lambda *_: None) == {}


def test_llm_cuts_only_inside_chunk_and_short_words():
    words = words_from("그 그래서 이 버튼을 누르면")
    words.append(Word(10.0, 13.0, "그"))  # 3초짜리 단어는 Claude 가 골라도 자르지 않는다
    llm = FakeLLM({"cuts": [{"index": 0, "reason": "말더듬"}, {"index": 5, "reason": "필러"},
                            {"index": 99, "reason": "범위 밖"}]})
    cuts = decide_fillers(words, llm, log=lambda *_: None)
    assert cuts == {0: "말더듬"}
    assert "[후보]" in llm.calls[0][1]


def test_llm_failure_falls_back_to_rules(unavailable):
    words = words_from("어 안녕하세요")
    cuts = decide_fillers(words, FakeLLM(error=unavailable), log=lambda *_: None)
    assert cuts == {0: "필러"}


# ───────────── 남길 구간 ─────────────

def test_keep_segments_merge_close_words():
    words = [Word(1.0, 1.4, "안녕"), Word(1.5, 2.0, "하세요")]
    segs = compute_keep_segments(words, {}, [], duration=10, pad=0.1, max_pause=0.45, min_segment=0.2)
    assert segs == [(0.9, 2.1)]


def test_keep_segments_split_on_long_pause():
    words = [Word(1.0, 1.5, "하나"), Word(4.0, 4.5, "둘")]
    segs = compute_keep_segments(words, {}, [], duration=10, pad=0.1, max_pause=0.45, min_segment=0.2)
    assert segs == [(0.9, 1.6), (3.9, 4.6)]


def test_cut_filler_not_reintroduced_by_pad():
    # "어"(1.5~1.9)를 자르면 앞뒤 pad 가 필러 소리를 다시 끌어오지 않아야 한다
    words = [Word(1.0, 1.45, "그래서"), Word(1.5, 1.9, "어"), Word(1.95, 2.4, "이렇게")]
    segs = compute_keep_segments(words, {1: "필러"}, [], duration=10, pad=0.12, max_pause=0.45, min_segment=0.2)
    assert len(segs) == 2
    assert segs[0][1] <= 1.5
    assert segs[1][0] >= 1.9


def test_long_silence_inside_word_timestamps_is_trimmed():
    # Whisper 타임스탬프가 무음까지 늘어난 경우: 음량 기준으로 한 번 더 깎는다
    words = [Word(0.0, 5.0, "길게늘어진단어")]
    segs = compute_keep_segments(words, {}, [(1.0, 4.0)], duration=10, pad=0.1, max_pause=0.45, min_segment=0.2)
    assert segs == [(0.0, 1.1), (3.9, 5.1)]


def test_tiny_fragments_dropped_and_duration_clamped():
    words = [Word(0.0, 0.05, "아"), Word(5.0, 9.95, "끝")]
    segs = compute_keep_segments(words, {}, [], duration=10, pad=0.0, max_pause=0.45, min_segment=0.2)
    assert segs == [(5.0, 9.95)]
    segs = compute_keep_segments([Word(9.8, 10.0, "끝")], {}, [], duration=10, pad=0.12,
                                 max_pause=0.45, min_segment=0.2)
    assert segs[-1][1] == 10


def test_no_words_keeps_everything():
    assert compute_keep_segments([], {}, [], 12.5, 0.1, 0.45, 0.2) == [(0.0, 12.5)]


def test_snap_to_frames():
    segs = snap_to_frames([(0.01, 1.01), (2.0, 2.01)], fps=30)
    assert segs == [(0.0, 1.0)]  # 두 번째는 0프레임이 되어 사라진다
    for a, b in snap_to_frames([(0.123, 4.567)], fps=29.97):
        assert abs(a * 29.97 - round(a * 29.97)) < 1e-9
        assert abs(b * 29.97 - round(b * 29.97)) < 1e-9


# ───────────── TimeMap ─────────────

def test_timemap_to_cut():
    tm = TimeMap([(1.0, 2.0), (5.0, 7.0)])
    assert tm.total == pytest.approx(3.0)
    assert tm.to_cut(1.5) == pytest.approx(0.5)
    assert tm.to_cut(6.0) == pytest.approx(2.0)
    assert tm.to_cut(3.0) is None


def test_timemap_remap_words_skips_cut_and_clamps():
    tm = TimeMap([(1.0, 2.0), (5.0, 7.0)])
    words = [Word(1.1, 1.5, "남김"), Word(1.6, 1.8, "어"), Word(1.9, 2.3, "걸침"), Word(3.0, 3.5, "잘린곳"),
             Word(5.5, 6.0, "뒤")]
    out = tm.remap_words(words, {1: "필러"})
    assert [w.text for w in out] == ["남김", "걸침", "뒤"]
    assert out[1].start == pytest.approx(0.9) and out[1].end == pytest.approx(0.9)  # 구간 밖 끝은 시작에 붙인다
    assert out[2].start == pytest.approx(1.5) and out[2].end == pytest.approx(2.0)


# ───────────── 무음 감지 ─────────────

def test_detect_silences(tmp_path):
    sr = 16000
    t = np.arange(sr) / sr
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    rng = np.random.default_rng(0)
    quiet = 0.001 * rng.standard_normal(sr)
    audio = np.concatenate([tone, quiet, tone])  # 1초 말 / 1초 무음 / 1초 말
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    sil = detect_silences(path, min_len=0.45)
    assert len(sil) == 1
    s, e = sil[0]
    assert s == pytest.approx(1.0, abs=0.04) and e == pytest.approx(2.0, abs=0.04)

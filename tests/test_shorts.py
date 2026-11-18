"""쇼츠(세로) 만들기의 순수 로직: 구간 고르기, 시간 옮기기, 얼굴 경로 다듬기, crop 식."""
from autoedit.shorts import (crop_x_expr, fallback_pick, pick_highlight, shift_items, shift_words,
                             smooth_path)
from autoedit.transcribe import Word


def sents_of(spec: list[tuple[float, float, str]]) -> list[dict]:
    return [{"start": s, "end": e, "text": t, "word_range": [k, k]} for k, (s, e, t) in enumerate(spec)]


# 10초짜리 문장 8개: 3~5번이 말이 가장 촘촘하다
SENTS = sents_of([(i * 10.0, i * 10.0 + 9.0, "가" * (40 if 3 <= i <= 5 else 10)) for i in range(8)])


def test_fallback_picks_dense_window_within_limits():
    i, j = fallback_pick(SENTS, 25, 35)
    assert (i, j) == (3, 5)


def test_fallback_without_valid_window_takes_from_start():
    short = sents_of([(0, 4, "하나"), (5, 9, "둘")])
    assert fallback_pick(short, 30, 60) == (0, 1)


def test_pick_uses_claude_when_valid(fake_llm):
    llm = fake_llm({"start_index": 1, "end_index": 4, "title": "핵심 세 가지", "reason": "질문으로 시작"})
    p = pick_highlight(SENTS, llm, 30, 60, log=lambda *_: None)
    assert (p["i"], p["j"], p["title"], p["by"]) == (1, 4, "핵심 세 가지", "claude")


def test_pick_rejects_too_long_claude_answer(fake_llm):
    llm = fake_llm({"start_index": 0, "end_index": 7, "title": "전부", "reason": "x"})   # 79초 > 60초
    p = pick_highlight(SENTS, llm, 30, 60, log=lambda *_: None)
    assert p["by"] == "rule" and SENTS[p["j"]]["end"] - SENTS[p["i"]]["start"] <= 60


def test_pick_falls_back_when_claude_fails(fake_llm, unavailable):
    p = pick_highlight(SENTS, fake_llm(error=unavailable), 30, 60, log=lambda *_: None)
    assert p["by"] == "rule"


def test_pick_title_never_shows_beep(fake_llm):
    sents = sents_of([(0, 9, "(삐-) 번으로 연락 주세요"), (10, 39, "가" * 50)])
    p = pick_highlight(sents, None, 30, 60, log=lambda *_: None)
    assert "(삐-)" not in p["title"]


def test_short_video_uses_whole():
    sents = sents_of([(0, 9, "가" * 20), (10, 19, "나" * 20), (20, 24, "다" * 20)])
    p = pick_highlight(sents, None, 30, 60, log=lambda *_: None)
    assert (p["i"], p["j"]) == (0, 2)           # 영상 전체가 쇼츠 길이 안쪽 → 통째로


def test_shift_items_moves_and_clips_to_segment():
    items = [{"start": 5, "end": 12, "x": 1}, {"start": 50, "end": 60}, {"start": 18, "end": 25}]
    out = shift_items(items, 10, 20)
    assert [(o["start"], o["end"]) for o in out] == [(0.0, 2), (8, 10)]
    assert out[0]["x"] == 1 and items[0]["start"] == 5          # 원본은 그대로


def test_shift_words_keeps_only_segment():
    words = [Word(1, 2, "a"), Word(10.5, 11, "b"), Word(30, 31, "c")]
    assert [(w.start, w.text) for w in shift_words(words, 10, 20)] == [(0.5, "b")]


def test_smooth_path_none_when_faces_rare():
    samples = [(k * 0.5, 0.5 if k == 3 else None) for k in range(20)]
    assert smooth_path(samples) is None


def test_smooth_path_ignores_jitter_and_fills_gaps():
    xs = [0.50, 0.51, None, 0.49, 0.50, 0.52, 0.50, 0.80, 0.81, 0.80, 0.79, 0.80]
    path = smooth_path([(k * 0.5, x) for k, x in enumerate(xs)])
    values = sorted({round(c, 2) for _, c in path})
    assert len(values) == 2 and values[0] < 0.55 and values[1] > 0.75   # 작은 흔들림은 무시, 큰 이동만


def test_crop_expr_clamps_inside_frame():
    expr = crop_x_expr([(0.0, 0.0), (5.0, 1.0)], src_w=1920, crop_w=608)
    assert expr.startswith("0.0") and "+1312.0*" in expr          # 왼쪽 끝 → 오른쪽 끝(1920-608)


def test_fallback_avoids_greeting_start():
    sents = sents_of([(0, 9, "안녕하세요, 오늘은 세 가지를 볼게요."), (10, 19, "첫째는 출결 관리입니다."),
                      (20, 29, "둘째는 수련비입니다."), (30, 39, "셋째는 승급입니다."), (40, 49, "감사합니다.")])
    i, j = fallback_pick(sents, 25, 35)
    assert i == 1


def test_fallback_title_drops_greeting_and_cuts_at_word():
    from autoedit.shorts import _fallback_title
    t = _fallback_title("안녕하세요, 오늘은 태권도장 운영에서 꼭 챙겨야 할 세 가지를 이야기해 볼게요.")
    assert t == "태권도장 운영에서 꼭 챙겨야" and len(t) <= 16

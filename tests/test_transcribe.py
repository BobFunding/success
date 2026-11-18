from autoedit.transcribe import Word, _Seg, merge_language_passes


def _seg(start, end, lp, *texts):
    step = (end - start) / len(texts)
    return _Seg(start, end, lp, [Word(start + i * step, start + (i + 1) * step, t) for i, t in enumerate(texts)])


def test_merge_picks_more_confident_language_per_region():
    passes = {
        # 한국어 전사: 앞 인사는 잘 들림, 영어 구간은 번역해서 지어냄(확신도 낮음)
        "ko": [_seg(0.0, 3.3, -0.74, "한국", "남자", "특징"), _seg(30.0, 36.0, -0.91, "너무", "슬픈", "것")],
        # 영어 전사: 영어 구간은 확신도 높음, 앞 인사 구간은 없음
        "en": [_seg(3.2, 11.4, -0.57, "What's", "the", "most"), _seg(31.0, 36.0, -0.37, "they're", "so", "stylish")],
    }
    words = merge_language_passes(passes)
    assert [w.text for w in words] == ["한국", "남자", "특징", "What's", "the", "most", "they're", "so", "stylish"]
    assert all(a.start <= b.start for a, b in zip(words, words[1:]))


def test_merge_drops_edge_word_owned_by_better_segment():
    passes = {"ko": [_seg(0.0, 2.0, -0.5, "가", "나")], "en": [_seg(1.8, 3.0, -0.9, "x", "y", "z")]}
    # 겹침이 30% 미만이라 두 구간 모두 남지만, 겹친 가장자리 단어("x", 중심 2.0초)는 확신도 높은 쪽 구간 몫
    words = merge_language_passes(passes)
    assert [w.text for w in words] == ["가", "나", "y", "z"]

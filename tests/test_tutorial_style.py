"""튜토리얼 메이커 9단계: 참고 영상 스타일 카드 — 측정값 → 엔진 설정, 1편을 넣으면 1편 설정."""
import json
from pathlib import Path

import pytest

from autoedit.tutorial import rules as R
from autoedit.tutorial import style as ST


def card(cps=3.84, gap=0.40, zoom=1.5, zmax=1.66, n_zoom=7, subs=True, music=False, ratio="가로", move=0.03):
    return {"이름": "t", "영상": {"크기": "1920×1080", "비율": ratio, "fps": 30, "길이": 90},
            "측정": {"장면전환": {"횟수": 3, "평균간격": 14, "방식": "컷"},
                   "확대": {"횟수": n_zoom, "분당": 4, "배율": zoom, "최대배율": zmax, "이동": move},
                   "자막": {"있음": subs, "위치": 0.9, "크기": 0.05, "글자색": "#FFFFFF", "상자색": "#122050", "상자": True},
                   "말": {"말": True, "초당글자": cps, "문장사이쉼": gap, "첫말": 0, "배경음악": music}, "인트로": 10, "색감": {}}}


def test_episode1_measurements_give_episode1_settings():
    a, ref, cant = ST.mapping(card())
    assert a == {"rules": {"확대": 1.6, "최대확대": 2.0, "문장사이쉼": 0.55, "눌러주세요뒤쉼": 0.55}, "speed": 0, "subtitles": True}
    assert R.merged(a["rules"])["확대"] == R.DEFAULT["확대"] and R.merged(a["rules"])["문장사이쉼"] == R.DEFAULT["문장사이쉼"]


def test_style_ranges_and_cannot_follow():
    a, ref, cant = ST.mapping(card(cps=6.0, gap=2.5, zoom=3.0, zmax=4.0, music=True, ratio="세로", move=0.2))
    assert a["speed"] == 10 and a["rules"]["문장사이쉼"] == 1.5 and a["rules"]["확대"] == 2.2 and a["rules"]["최대확대"] == 2.6
    assert any("배경음악" in c for c in cant) and any("카메라 이동" in c for c in cant) and any("세로" in r for r in ref)
    a, *_ = ST.mapping(card(n_zoom=0))
    assert a["rules"]["확대"] == 1.0                                                   # 확대가 없는 영상이면 확대 안 함


def test_style_layer_cannot_turn_off_safety():
    r = R.merged({}, {"안전": {"개인정보흐림": False}, "확대": 1.2}, {"확대": 1.4})
    assert r["안전"]["개인정보흐림"] and r["확대"] == 1.4                               # 브랜드(뒤 층)가 스타일을 덮음


def test_cards_saved_without_content(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "STYLES", tmp_path)
    c = card(); c["적용"], c["참고만"], c["따라할수없음"] = ST.mapping(c)
    p = ST.save(c)
    assert ST.get(p.stem)["적용"]["speed"] == 0 and [x["key"] for x in ST.cards()] == [p.stem]
    txt = p.read_text(encoding="utf-8")
    assert "자막" in txt and "글" not in json.loads(txt)["측정"]["자막"]               # 자막 글자는 남기지 않음

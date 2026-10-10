"""튜토리얼 메이커 5단계: 발음 비교, 검수 규칙(클릭 위치·시각·개인정보 값), 팝업 닫기 동작 빼기."""
from pathlib import Path

from autoedit.tutorial import qa
from autoedit.tutorial import scenario as S
from autoedit.tutorial.demo_record import clean_events

EP1 = Path(__file__).resolve().parents[1] / "tutorials" / "ep1" / "scenario.yaml"


def test_compare_heard_ignores_spacing_and_digits():
    r, bad = qa.compare_heard("회원 유형이 네 가지 나오는데요, 관장님을 눌러 주세요.", "회원 유형이 4가지 나오는데요. 관장님을 눌러주세요.")
    assert bad == []                           # '네 가지' 를 '4가지' 로 받아 적은 것은 발음 문제가 아님
    r, bad = qa.compare_heard("생년월일과 성별, 단은 목록에서 골라 주세요.", "생년월일과 성별, 다른 목록에서 골라주세요")
    assert bad == ["단은"]
    r, bad = qa.compare_heard("안녕하세요, 태권 월드입니다.", "안녕하세요 태권널드입니다")
    assert bad == ["월드입니다"] and r > 0.8


def test_suggest():
    assert "띄어" in qa.suggest("태권월드입니다", "태권 월드")
    assert "한글" in qa.suggest("ID")
    assert "숫자" in qa.suggest("3단계")


def _rec():
    return {"marks": {"body_start": 0.0},
            "lines": [{"key": "S1", "t": 1.0}, {"key": "S2", "t": 6.0}],
            "clicks": [{"t": 4.5, "x": 150, "y": 150}, {"t": 9.0, "x": 900, "y": 900, "kind": "목록"},
                       {"t": 9.5, "x": 520, "y": 520}],
            "spots": [{"start": 2.0, "end": 5.0, "x": 100, "y": 100, "w": 100, "h": 100},
                      {"start": 7.0, "end": 10.0, "x": 500, "y": 500, "w": 50, "h": 50}]}


def test_check_spots_skips_open_list_items():
    r = qa.check_spots(_rec())
    assert r["판정"] == "ok" and r["내용"].startswith("2/2")
    rec = _rec()
    rec["clicks"].append({"t": 4.0, "x": 900, "y": 100})
    r = qa.check_spots(rec)
    assert r["판정"] == "warn" and "4.0초" in r["내용"]


def test_check_timing():
    sc = S.load(EP1)
    sc.scenes = sc.scenes[:2]                  # S1, S2 (클릭)
    dur = {"S1": 4.0, "S2": 4.0}
    assert qa.check_timing(sc, _rec(), dur)["판정"] == "ok"
    late = _rec()
    late["clicks"][-1]["t"] = 11.5             # S2 문장(6~10초)보다 한참 뒤
    late["clicks"][1]["t"] = 11.4
    assert qa.check_timing(sc, late, dur)["판정"] == "warn"


def test_private_values_never_include_passwords():
    sc = S.load(EP1)
    vals = qa.private_values(sc)
    assert "01000000000" in vals and "000000" in vals and "태권" not in vals   # 2글자 이하 값은 오탐이 많아 뺌
    assert not any(v.startswith("@") for v in vals)


def _ev(ev, t, **k):
    base = dict(ev=ev, t=t, url="http://s/", tag="button", role="", type="", name="", text="", label="", placeholder="",
                aria="", sel=[], box={"x": 0, "y": 0, "w": 10, "h": 10}, combo=-1, option=-1, heading="", hit=True)
    base.update(k)
    return base


def test_demo_drops_popup_close_clicks():
    evs = [_ev("click", 0, text="오늘 하루 보지 않기", sel=["#a"]), _ev("click", 100, text="닫기", sel=["#b"]),
           _ev("click", 200, tag="a", text="회원가입", sel=["#c"])]
    out = clean_events(evs, [])
    assert [o["name"] for o in out] == ["회원가입"]

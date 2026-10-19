"""튜토리얼 메이커: 장면 표 읽기·검사, 1편 기준값 유지, 녹화·편집 계산 조각."""
import sys
from pathlib import Path

import pytest

from autoedit.tutorial import scenario as S
from autoedit.tutorial.compose import Composer, _count, srt_time, ts
from autoedit.tutorial.recorder import Recorder, privacy_css

ROOT = Path(__file__).resolve().parents[1]
EP1 = ROOT / "tutorials" / "ep1" / "scenario.yaml"


def _write(tmp_path, text):
    p = tmp_path / "s.yaml"
    p.write_text(text, encoding="utf-8")
    return p


BASE = """제목: 테스트, [2단계]면 끝!
주소: https://example.com/
단계이름: [하나, 둘]
인트로: [{키: I1, 말: 안녕}, {키: I2, 말: 오늘은}]
아웃트로: [{키: O1, 말: 끝}, {키: O2, 말: 안녕히}]
장면:
"""


def test_ep1_scenario_matches_original_script():
    """1편 장면 표의 대본이 원래 lines.py 와 글자·속도·높낮이까지 같아야 한다."""
    sys.path.insert(0, str(ROOT / "tutorials" / "ep1"))
    from lines import LINES
    sc = S.load(EP1)
    assert [(l.key, l.text, l.rate, l.pitch) for l in sc.lines()] == [tuple(x) for x in LINES]
    assert sc.steps == ["가입 화면 찾기", "정보 입력하기", "약관 동의하고 등록"]
    assert sc.brand.background == ("#1B2559", "#405BEA") and sc.brand.accent == "#CC1424"
    assert sc.brand.point == "#54B4CC" and sc.brand.voice_rate == -8
    assert Path(sc.brand.logo).exists()
    assert [s.step for s in sc.scenes].count(2) == 8
    assert sc.title_plain == "관장님 회원가입, 3단계면 끝!"


def test_simple_scene_defaults(tmp_path):
    sc = S.load(_write(tmp_path, BASE + """  - {키: A, 단계: 1, 말: 누르세요, 동작: 클릭, 대상: 로그인}
  - {키: B, 단계: 2, 말: 적으세요, 동작: 입력, 대상: "input[name=id]", 값: demo}
"""))
    a, b = sc.scenes
    assert a.target == "로그인" and a.lead == 0.35 and a.spot_pad == 8 and a.gap == S.GAP
    assert b.fields[0].value == "demo" and b.fields[0].approach == -150 and b.fields[0].delay == 0.09
    assert sc.brand.name == "태권월드"          # 브랜드를 안 적으면 기본 브랜드


@pytest.mark.parametrize("scene, msg", [
    ("  - {키: A, 단계: 1, 말: 가, 동작: 날기}", "모르겠어요"),
    ("  - {키: A, 단계: 1, 말: 가, 동작: 클릭}", "누를 곳이 없어요"),
    ("  - {키: A, 단계: 3, 말: 가, 동작: 대기}", "벗어나요"),
    ("  - {키: I1, 단계: 1, 말: 가, 동작: 대기}", "겹쳐요"),
    ("  - {키: A, 말: 가, 동작: 대기}", "'단계'"),
    ("  - {키: A, 단계: 1, 말: 가, 동작: 선택}", "고를 목록"),
])
def test_scene_errors_are_plain_words(tmp_path, scene, msg):
    with pytest.raises(S.ScenarioError, match=msg):
        S.load(_write(tmp_path, BASE + scene + "\n"))


def test_steps_must_be_in_order(tmp_path):
    with pytest.raises(S.ScenarioError, match="순서"):
        S.load(_write(tmp_path, BASE + "  - {키: A, 단계: 2, 말: 가, 동작: 대기}\n  - {키: B, 단계: 1, 말: 나, 동작: 대기}\n"))


def test_subtitle_uses_written_brand_name():
    b = S.load(EP1).brand
    assert S.subtitle_text("안녕하세요, 태권 월드입니다.", b) == "안녕하세요, 태권월드입니다."


def test_privacy_css_covers_inputs_and_select_boxes():
    css = privacy_css(["input[name=last_name]", "input[name=dob]"])
    assert "input[name=last_name], input[name=dob] {" in css and "caret-color: transparent" in css
    assert "div[role=combobox]:has(+ input[name=dob])" in css
    assert privacy_css([]) == ""


def test_spot_union_like_episode1():
    sc = S.load(EP1)
    f3 = next(s for s in sc.scenes if s.key == "F3")
    f5 = next(s for s in sc.scenes if s.key == "F5")
    a = {"x": 100, "y": 50, "width": 300, "height": 40}
    z = {"x": 420, "y": 120, "width": 80, "height": 44}
    # 가로(기본): 첫 칸 높이, 끝 칸 오른쪽까지 / 왼쪽 늘리기
    assert Recorder._union([a, z], f5) == {"x": -8, "y": 50, "width": 508, "height": 40}
    # 세로: 첫 칸 너비, 끝 칸 아래까지
    assert Recorder._union([a, z], f3) == {"x": 100, "y": 50, "width": 300, "height": 114}


def test_card_row_matches_episode1():
    c = Composer.__new__(Composer)
    c.STEPS = ["가", "나", "다"]
    cw, ch, cx = c.card_row()
    assert (cw, ch) == (760, 130) and cx == [(2560 - 3 * 760 - 100) // 2 + i * 810 for i in range(3)]
    c.STEPS = ["가"] * 5
    cw, _, cx = c.card_row()
    assert cx[0] >= 0 and cx[-1] + cw <= 2560


def test_time_formats():
    assert ts(61.234) == "0:01:01.23" and srt_time(61.234) == "00:01:01,234"
    assert _count(3) == "세" and _count(12) == "12"

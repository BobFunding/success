"""튜토리얼 메이커 4단계: 규칙 3층, 화면 서버(주소 제한·파일 제한), 읽힘 검사."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from autoedit.tutorial import rules as R
from autoedit.tutorial import scenario as S
from autoedit.tutorial import server as SV

EP1 = Path(__file__).resolve().parents[1] / "tutorials" / "ep1" / "scenario.yaml"


def test_rules_layers_and_lock():
    r = R.merged({"문장사이쉼": 0.6, "안전": {"개인정보흐림": False}}, {"확대": 1.4}, {"문장사이쉼": 0.5, "모르는것": 1})
    assert r["문장사이쉼"] == 0.5 and r["확대"] == 1.4            # 아래 층이 위를 덮음
    assert r["안전"] == {"개인정보흐림": True, "저장차단": True}    # 잠긴 규칙은 못 끔
    assert "모르는것" not in r
    assert R.merged() == R.DEFAULT


def test_default_rules_keep_episode1():
    sc = S.load(EP1)
    gaps = [s.gap for s in sc.scenes]
    assert R.apply(sc, R.merged()) == []
    assert [s.gap for s in sc.scenes] == gaps                       # 기본 규칙은 1편을 바꾸지 않음


def test_rules_apply_replacements_and_pause():
    sc = S.load(EP1)
    R.apply(sc, R.merged({"표현바꾸기": {"중복확인": "중복 확인"}, "눌러주세요뒤쉼": 1.0}))
    f2 = next(s for s in sc.scenes if s.key == "F2")
    s1 = next(s for s in sc.scenes if s.key == "S1")
    f1 = next(s for s in sc.scenes if s.key == "F1")
    assert "중복 확인을" in f2.line.text
    assert s1.gap == 1.0 and f1.gap == 0.33                         # 장면 표에 직접 적은 쉼은 그대로


def test_rules_warn_long_sentence():
    sc = S.load(EP1)
    w = R.warnings(sc, R.merged({"문장최대글자": 20}), total=200)
    assert any("1번 장면" in x for x in w) and any("분이에요" in x for x in w)


def test_contrast_check():
    assert SV.contrast("#FFFFFF", "#000000") == pytest.approx(21, rel=0.01)
    b = S.load_brand("taekwonworld")
    assert SV.contrast_report(b)["ok"]
    b.background = ("#F0F0F0", "#FFFFFF")
    assert not SV.contrast_report(b)["ok"]


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "USER_DIR", tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url, host=None):
    req = urllib.request.Request(url, headers={"Host": host} if host else {})
    with urllib.request.urlopen(req) as r:
        return r.status, r.read()


def test_server_state_and_page(srv):
    st, body = _get(srv + "/api/state")
    d = json.loads(body)
    assert st == 200 and d["rules"]["확대"] == 1.6 and "taekwonworld" in d["brands"]
    assert any(p["example"] for p in d["projects"])                  # 빈 화면 금지: 1편 예시
    st, page = _get(srv + "/")
    assert "튜토리얼 메이커" in page.decode()


def test_server_rejects_other_hosts_and_files(srv):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(srv + "/api/state", host="evil.example")                 # 다른 주소로 들어온 요청
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(srv + "/file?path=/etc/passwd")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(srv + "/../../etc/passwd")
    assert e.value.code == 404


def test_server_saves_rules(srv, tmp_path):
    req = urllib.request.Request(srv + "/api/rules/save", data=json.dumps({"rules": {"문장사이쉼": 0.7}}).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req).read())
    assert d["rules"]["문장사이쉼"] == 0.7
    assert "문장사이쉼: 0.7" in (tmp_path / "rules.yaml").read_text(encoding="utf-8")


def test_secrets_file_store(tmp_path, monkeypatch):
    from autoedit.tutorial import secrets as SEC
    monkeypatch.delenv("TUTORIAL_SECRET", raising=False)
    monkeypatch.setattr(SEC, "STORE", tmp_path / "s.json")
    monkeypatch.setattr(SEC, "_kr", lambda: None)                 # 운영체제 보관함이 없는 PC
    k = SEC.key_for("https://example.com/login", "#pw")
    assert k == "example.com|#pw" and SEC.key_for("https://a.com", "#pw", "@보관함:관리자") == "a.com|관리자"
    assert not SEC.has(k)
    assert SEC.put(k, "pa ss") == "이 PC 안 파일" and SEC.get(k) == "pa ss"
    sc = S.load(EP1)
    sc.scenes[5].fields[0].value = "@보관함"                    # F2 아이디 칸을 보관함 값으로 바꿔 봄
    need = SEC.needed(sc)
    assert need and need[0]["키"].startswith("taekwonworld.net|") and need[0]["있음"] is False


def test_repro_compares_per_scene_timing_not_accumulated_drift():
    """한 장면이 사이트 로딩으로 늦어져 뒤가 다 밀려도, 장면 안 박자가 같으면 같은 것으로 본다."""
    from autoedit.tutorial.repro import compare_logs
    def log(shift):
        lines = [{"key": "A", "t": 1.0}, {"key": "B", "t": 5.0 + shift}]
        return {"marks": {"body_start": 0.0}, "lines": lines,
                "clicks": [{"t": 2.0, "x": 10, "y": 10}, {"t": 6.0 + shift, "x": 20, "y": 20}],
                "spots": [{"start": 1.5, "end": 2.4, "x": 0, "y": 0, "w": 50, "h": 50},
                          {"start": 5.5 + shift, "end": 6.4 + shift, "x": 0, "y": 0, "w": 50, "h": 50}]}
    r = compare_logs(log(0.0), log(0.5))
    assert r["ok"] and r["drift"] == 0.5 and r["scene_t"] == 0.0
    bad = log(0.5)
    bad["clicks"][1]["t"] += 0.4                                        # 장면 안에서 박자가 다름
    assert not compare_logs(log(0.0), bad)["ok"]
    moved = log(0.0)
    moved["clicks"][0]["x"] = 40                                        # 누른 자리가 다름
    assert not compare_logs(log(0.0), moved)["ok"]


def test_server_export_needs_destination(srv):
    req = urllib.request.Request(srv + "/api/export", data=json.dumps({"path": str(EP1), "to": []}).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req).read())
    assert d["ok"] is False and "올릴 곳" in d["error"]
    pl = SV.platforms_view()
    assert len(pl) == 14 and {p["key"] for p in pl if p["default"]} == {"youtube", "web"}

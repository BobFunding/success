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
    assert len(pl) == 15 and {p["key"] for p in pl if p["default"]} == {"youtube", "web"}


def test_repro_tolerance_follows_original_code_noise():
    """허용치 = max(0.25초, 원래 코드끼리의 흔들림). 위치는 늘 0px 이어야 한다."""
    from autoedit.tutorial.repro import compare_logs
    def log(d):
        return {"marks": {"body_start": 0.0}, "lines": [{"key": "A", "t": 1.0}],
                "clicks": [{"t": 2.0 + d, "x": 10, "y": 10}],
                "spots": [{"start": 1.5, "end": 2.4, "x": 0, "y": 0, "w": 50, "h": 50}]}
    assert not compare_logs(log(0), log(0.3))["ok"]                       # 고정 0.25초면 실패
    noise = compare_logs(log(0), log(0.32), tol_t=99)["scene_t"]          # 원래 코드끼리 0.32초 흔들림
    r = compare_logs(log(0), log(0.3), tol_t=max(0.25, noise))
    assert r["ok"] and r["tol_t"] == 0.32
    assert not compare_logs(log(0), log(0.4), tol_t=max(0.25, noise))["ok"]


def test_purpose_templates_keep_customer_default():
    from autoedit.tutorial import sentences as T
    i, o = T.intro_outro("관장님 회원가입", 3, "태권 월드")
    assert i == ["안녕하세요, 태권 월드입니다.", "오늘은 관장님 회원가입 방법을, 세 단계로 알려 드릴게요."]   # 1편 그대로
    i, o = T.intro_outro("회원 등록", 3, "도서관", purpose="직원 교육")
    assert "업무 교육" in i[0] and "익혀" in i[1] and o[1] == "수고하셨습니다."
    i, o = T.intro_outro("회원 등록", 2, "", purpose="제품 소개")
    assert i[1] == "두 단계면 끝나요."


def test_report_masks_private_things():
    from autoedit.tutorial import ops
    job = {"kind": "make", "stage": "녹화", "running": False, "error": "실패 sk-ant-abcdefghijk 010-1234-5678",
           "log": ["메일 a.b@test.com 인증 482913"]}
    t = ops.report(job, EP1)
    assert "sk-ant-abc" not in t and "1234-5678" not in t and "a.b@test.com" not in t and "482913" not in t
    assert "장면 13개" in t and "taekwonworld.net" in t


def test_share_pack_and_unpack(tmp_path, monkeypatch):
    import zipfile
    from autoedit.tutorial import ops
    from autoedit.tutorial import scenario as S2
    monkeypatch.setattr(R, "USER_DIR", tmp_path / "u")
    monkeypatch.setattr(S2, "USER_BRANDS", tmp_path / "brands")
    src = tmp_path / "p" / "scenario.yaml"
    src.parent.mkdir()
    d = S2.yaml.safe_load(EP1.read_text(encoding="utf-8")) if hasattr(S2, "yaml") else __import__("yaml").safe_load(EP1.read_text(encoding="utf-8"))
    d["개인정보칸"] = ["#name"]
    d["장면"][0]["칸"] = [{"누를곳": "#name", "값": "진짜이름"}, {"누를곳": "#pw", "값": "@보관함"}]
    import yaml as Y
    src.write_text(Y.safe_dump(d, allow_unicode=True), encoding="utf-8")
    z = ops.pack(src, tmp_path / "p")
    names = zipfile.ZipFile(z).namelist()
    assert "scenario.yaml" in names and any(n.startswith("brand/") for n in names)
    assert "진짜이름" not in zipfile.ZipFile(z).read("scenario.yaml").decode()          # 개인정보 칸 값은 비움
    out = ops.unpack(z.read_bytes(), tmp_path / "projects")
    assert out.exists() and (tmp_path / "brands" / "taekwonworld.yaml").exists() is False   # 기본 제공 브랜드는 복사 안 함
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zz:
        zz.writestr("scenario.yaml", "제목: x")
        zz.writestr("../evil.txt", "x")
    with pytest.raises(ValueError):
        ops.unpack(bad.read_bytes(), tmp_path / "projects")


def test_series_links_next_episode(tmp_path):
    import yaml as Y
    from autoedit.tutorial import ops
    def mk(name, title):
        p = tmp_path / name / "scenario.yaml"
        p.parent.mkdir()
        d = Y.safe_load(EP1.read_text(encoding="utf-8"))
        d["제목"], d["파일이름"] = title, name
        d.pop("다음편", None)
        d["아웃트로"][-1]["말"] = "태권 월드였습니다."
        p.write_text(Y.safe_dump(d, allow_unicode=True), encoding="utf-8")
        return p
    a, b = mk("a", "관장님 회원가입, [3단계]면 끝!"), mk("b", "로그인, [2단계]면 끝!")
    ps = [a, b]
    ops.set_series(b, "태권월드 사용법", 2, ps)
    ops.set_series(a, "태권월드 사용법", 1, ps)
    da = Y.safe_load(a.read_text(encoding="utf-8"))
    assert da["다음편"] == "로그인" and da["아웃트로"][-1]["말"] == "다음 영상에서는 로그인 방법을 알려 드릴게요. 태권 월드였습니다."
    assert "다음편" not in Y.safe_load(b.read_text(encoding="utf-8"))
    assert [e["편"] for e in ops.series_list(ps)["태권월드 사용법"]] == [1, 2]


def test_site_change_detection(tmp_path):
    import json as J
    from autoedit.tutorial import maker
    def log(dx=0.0, extra=False):
        cl = [{"t": 1.5, "x": 100, "y": 100}, {"t": 3.5, "x": 400 + dx, "y": 300}]
        if extra:
            cl.append({"t": 3.8, "x": 10, "y": 10})
        return {"lines": [{"key": "A", "t": 1.0}, {"key": "B", "t": 3.0}], "clicks": cl}
    (tmp_path / "log_rec.json").write_text(J.dumps(log()))
    (tmp_path / "log_dry.json").write_text(J.dumps(log(4)))
    assert maker.site_changes(tmp_path) == []                                  # 몇 px 는 같은 것
    (tmp_path / "log_dry.json").write_text(J.dumps(log(60)))
    assert [c["키"] for c in maker.site_changes(tmp_path)] == ["B"]
    (tmp_path / "log_dry.json").write_text(J.dumps(log(0, extra=True)))
    assert "횟수" in maker.site_changes(tmp_path)[0]["이유"]


def test_resume_marker_and_batch_keep_going(tmp_path, monkeypatch):
    monkeypatch.setattr(SV, "work_dir", lambda p: tmp_path / p.parent.name)
    seen = []
    def fake(job, path, ch, preview=False, allow_real=False):
        seen.append((path.parent.name, (tmp_path / path.parent.name / "작업중.json").exists(), ch))
        if path.parent.name == "bad":
            raise ValueError("사이트가 바뀌었어요")
        return {"final": "x.mp4"}
    monkeypatch.setattr(SV, "_job_make", fake)
    (tmp_path / "ok").mkdir(); (tmp_path / "ok" / "choices.json").write_text('{"voice": "선희 · 밝게"}', encoding="utf-8")
    class J:
        def update(self, **k): pass
        def log(self, m): pass
    monkeypatch.setattr(SV.S, "load", lambda p: type("X", (), {"title_plain": p.parent.name})())
    r = SV.job_batch(J(), [{"path": str(tmp_path / "bad" / "scenario.yaml")}, {"path": str(tmp_path / "ok" / "scenario.yaml")}])
    assert [x["ok"] for x in r["batch"]] == [False, True]                      # 한 편이 멈춰도 다음 편
    assert seen[0][1] and seen[1][2] == {"voice": "선희 · 밝게"}               # 만드는 동안 표시, 지난번 선택 그대로
    assert not (tmp_path / "ok" / "작업중.json").exists() and not (tmp_path / "bad" / "작업중.json").exists()


def test_update_check_counts_new_commits(tmp_path, monkeypatch):
    import subprocess as sp
    up, me = tmp_path / "up", tmp_path / "me"
    g = lambda *a, cwd: sp.run(["git", *a], cwd=cwd, check=True, capture_output=True)
    up.mkdir(); g("init", "-q", "-b", "main", cwd=up)
    g("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "1", cwd=up)
    g("clone", "-q", str(up), str(me), cwd=tmp_path)
    g("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "2", cwd=up)
    monkeypatch.setattr(SV, "ROOT", me)
    assert SV.update_check() == {"ok": True, "behind": 1, "branch": "main"}
    assert SV.update_apply()["ok"] and SV.update_check()["behind"] == 0
    monkeypatch.setattr(SV, "ROOT", tmp_path / "nogit")
    assert SV.update_check()["ok"] is False


def test_quality_and_device_only_during_make(monkeypatch, tmp_path):
    import os
    from autoedit.tutorial import maker
    from autoedit.tutorial import recorder as RC
    seen = []
    monkeypatch.setattr(maker, "_make", lambda *a: seen.append((RC.W, RC.H, RC.SCALE, RC.DEVICE, os.environ.get("TUTORIAL_CAPTURE"), a[-2], a[-1])) or {})
    monkeypatch.delenv("TUTORIAL_CAPTURE", raising=False)
    maker.make(None, tmp_path)
    maker.make(None, tmp_path, quality="4K")
    maker.make(None, tmp_path, device="아이폰")
    assert seen[0] == (1920, 1080, 1.5, "PC", None, "1440p", "PC")                  # 기본은 1편 그대로
    assert seen[1][:5] == (1920, 1080, 2.0, "PC", "frames")                         # 4K: 3840x2160 로 찍음
    assert seen[2][:5] == (390, 844, 3.0, "아이폰", "frames")
    assert (RC.W, RC.H, RC.SCALE, RC.DEVICE) == (1920, 1080, 1.5, "PC") and "TUTORIAL_CAPTURE" not in os.environ


def test_composer_quality_sizes():
    from autoedit.tutorial import compose as C
    assert C.QUALITY == {"1440p": 1.0, "4K": 1.5, "8K": 3.0}
    assert {k: (int(C.W * v), int(C.H * v)) for k, v in C.QUALITY.items()} == {"1440p": (2560, 1440), "4K": (3840, 2160), "8K": (7680, 4320)}

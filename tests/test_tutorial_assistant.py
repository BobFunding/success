"""튜토리얼 메이커 8단계: AI 도우미(키 있을 때/없을 때)와 다국어."""
import json
import urllib.request
from pathlib import Path

import pytest

from autoedit.tutorial import assistant as A
from autoedit.tutorial import langs as LG
from autoedit.tutorial import scenario as S

EP1 = Path(__file__).resolve().parents[1] / "tutorials" / "ep1" / "scenario.yaml"


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    from autoedit.tutorial import secrets as SEC
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "TUTORIAL_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(SEC, "STORE", tmp_path / "s.json")
    monkeypatch.setattr(SEC, "_kr", lambda: None)
    monkeypatch.setattr("autoedit.llm._has_credentials", lambda: bool(__import__("os").environ.get("ANTHROPIC_API_KEY")))
    yield
    __import__("os").environ.pop("ANTHROPIC_API_KEY", None)        # ensure_key 가 넣은 것을 치움


def test_without_key_ai_is_off_with_plain_message():
    with pytest.raises(A.LLMUnavailable, match="키"):
        A.get_llm()
    assert "원" in A.estimate("explore")["text"] and A.estimate("translate", 20)["usd"] < 0.2


def test_key_from_vault_turns_ai_on(monkeypatch):
    from autoedit.tutorial import secrets as SEC
    SEC.put(A.KEY, "sk-ant-test-" + "x" * 30)
    assert A.ensure_key() and __import__("os").environ["ANTHROPIC_API_KEY"].startswith("sk-ant-test-")
    assert A.get_llm().available


def test_polish_returns_only_changed_lines(fake_llm):
    llm = fake_llm({"items": [{"key": "S1", "text": "먼저, 오른쪽 위 로그인 관장 버튼을 눌러 주세요."},
                              {"key": "S2", "text": "그대로"}, {"key": "없는키", "text": "x"}]})
    out = A.polish(llm, {"S1": "먼저, 첫 화면 오른쪽에 있는, 로그인 관장 버튼을 눌러 주세요.", "S2": "그대로"}, "차분", "태권월드")
    assert out == {"S1": "먼저, 오른쪽 위 로그인 관장 버튼을 눌러 주세요."}
    assert "차분" in llm.calls[0][0] and "태권월드" in llm.calls[0][0]


def test_translate_keeps_keys(fake_llm):
    llm = fake_llm({"items": [{"key": "제목", "text": "How to sign up"}, {"key": "S1", "text": "Click Log in (로그인)."}]})
    out = A.translate(llm, {"제목": "회원가입", "S1": "로그인을 눌러 주세요.", "S2": "둘째"}, "en", "태권월드")
    assert out == {"제목": "How to sign up", "S1": "Click Log in (로그인)."}
    assert "English" in llm.calls[0][0]


def test_store_secrets_fills_vault_slots():
    from autoedit.tutorial import secrets as SEC
    sc = {"주소": "https://a.com/", "로그인주소": "https://a.com/login",
          "미리하기": [{"칸": [{"대상": "#pw", "값": "@보관함"}]}], "장면": [{"누를곳": "#x", "값": "abc"}]}
    assert A.store_secrets(sc, ["pa55"]) == 1 and SEC.get("a.com|#pw") == "pa55"


def test_translations_and_srt(tmp_path):
    sc = S.load(EP1)
    src = LG.source(sc)
    assert src["제목"] == sc.title_plain and src["단계1"] == sc.steps[0] and "S1" in src
    LG.save(tmp_path, "en", {"S1": "Click the Log in (로그인) button.", "제목": "Sign up", "빈칸": "  "})
    assert LG.load(tmp_path) == {"en": {"S1": "Click the Log in (로그인) button.", "제목": "Sign up"}}
    assert "S2" in LG.missing(sc, LG.load(tmp_path)["en"])
    with pytest.raises(ValueError):
        LG.save(tmp_path, "xx", {})
    tl = {"lines": [{"key": "S1", "t": 10.2, "dur": 3.0}, {"key": "S2", "t": 14.0, "dur": 2.0}], "total": 20}
    txt = LG.srt(tl, LG.load(tmp_path)["en"], tmp_path / "a.srt").read_text(encoding="utf-8")
    assert txt.startswith("1\n00:00:10,200 --> 00:00:13,200\nClick") and "S2" not in txt


def test_server_ai_start_asks_for_key(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from autoedit.tutorial import rules as R
    from autoedit.tutorial import server as SV
    monkeypatch.setattr(R, "USER_DIR", tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())
        r = post("/api/ai/start", {"url": "http://x", "goal": "가입"})
        assert r["ok"] is False and r["need_key"]
        assert post("/api/key", {"name": "anthropic", "value": "짧음"})["ok"] is False
        st = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert st["keys"] == {"openai": False, "anthropic": False} and "원" in st["ai_cost"]
        assert any(v["kind"] == "silent" for v in st["voice_list"])
    finally:
        httpd.shutdown()


def test_spoken_drops_korean_screen_words():
    assert LG.spoken("Click Instructor (관장님).") == "Click Instructor."
    assert LG.spoken("click the Sign up (회원가입) button below.") == "click the Sign up button below."
    assert LG.spoken("Agree (all) now") == "Agree (all) now"                   # 한국어가 아닌 괄호는 그대로

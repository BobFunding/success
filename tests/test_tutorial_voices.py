"""튜토리얼 메이커 8단계: 목소리 고르기 — 자막만, 내 목소리, 유료 음성(키 있을 때만), 다시 만들지 않기."""
import json
import subprocess
from pathlib import Path

import pytest

from autoedit.ffmpeg_utils import FFMPEG
from autoedit.narration import Line
from autoedit.tutorial import voices as V


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    from autoedit.tutorial import secrets as SEC
    for k in ("OPENAI_API_KEY", "TUTORIAL_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(SEC, "STORE", tmp_path / "s.json")
    monkeypatch.setattr(SEC, "_kr", lambda: None)


def test_choices_without_and_with_paid_key(tmp_path):
    names = [c["name"] for c in V.choices()]
    assert names[:3] == ["현수 · 차분", "선희 · 밝게", "인준 · 또박또박"]          # 저장된 선택이 풀리지 않게 그대로
    assert V.MINE_NAME in names and V.SILENT_NAME in names
    assert not any(c["kind"] == "paid" for c in V.choices())                      # 키 없으면 유료 목소리 숨김
    from autoedit.tutorial import secrets as SEC
    SEC.put(V.OPENAI_KEY, "sk-test-" + "x" * 30)
    assert any(c["kind"] == "paid" for c in V.choices())


def test_read_seconds_matches_speech_pace():
    assert V.read_seconds("네") == 1.6                                             # 최소
    long = "먼저, 첫 화면 오른쪽에 있는, 로그인 관장 버튼을 눌러 주세요."
    assert 4.5 < V.read_seconds(long) < 6.5                                       # 현수 목소리 5.7초 언저리


def test_silent_makes_quiet_wavs(tmp_path):
    lines = [Line("A", "안녕하세요, 반갑습니다."), Line("B", "버튼을 눌러 주세요.")]
    V.synthesize(lines, tmp_path, tmp_path / "n", V.SILENT, 0, log=lambda *a: None)
    for ln in lines:
        assert Path(ln.path).exists() and abs(ln.duration - V.read_seconds(ln.text)) < 0.01


def test_my_voice_needs_every_line_and_cleans_up(tmp_path):
    lines = [Line("A", "첫 문장"), Line("B", "둘째 문장")]
    d = V.my_voice_dir(tmp_path)
    d.mkdir()
    # 앞뒤 1초 무음 + 가운데 1.5초 소리(사람 목소리 대신 톤)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=48000:cl=mono:d=1[s1];sine=f=220:d=1.5:r=48000[t];anullsrc=r=48000:cl=mono:d=1[s2];[s1][t][s2]concat=n=3:v=0:a=1",
                    "-t", "3.5", str(d / "A.wav")], check=False)
    if not (d / "A.wav").exists():   # lavfi 그래프 문법이 다른 ffmpeg
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=1.5:r=48000",
                        "-af", "adelay=1000,apad=pad_dur=1", str(d / "A.wav")], check=True)
    with pytest.raises(ValueError, match="B"):
        V.synthesize(lines, tmp_path, tmp_path / "n", V.MINE, 0)
    (d / "B.wav").write_bytes((d / "A.wav").read_bytes())
    V.synthesize(lines, tmp_path, tmp_path / "n", V.MINE, 0, log=lambda *a: None)
    assert 1.3 < lines[0].duration < 2.0                                           # 앞뒤 무음을 걷어 냄
    f1 = V.fingerprint(V.MINE, 0, tmp_path)
    (d / "B.wav").write_bytes((d / "A.wav").read_bytes() + b"")
    import os
    os.utime(d / "B.wav", (1, 1))
    assert V.fingerprint(V.MINE, 0, tmp_path) != f1                               # 다시 녹음하면 다시 만든다
    assert V.fingerprint("ko-KR-HyunsuMultilingualNeural", -8, tmp_path) == {"voice": "ko-KR-HyunsuMultilingualNeural", "rate": -8}


def test_paid_voice_without_key_says_so(tmp_path):
    with pytest.raises(ValueError, match="OpenAI 키"):
        V.synthesize([Line("A", "문장")], tmp_path, tmp_path / "n", "openai:onyx", 0)


def test_server_saves_recording_only_for_known_lines(tmp_path, monkeypatch):
    import base64
    from autoedit.tutorial import server as SV
    ep1 = Path(__file__).resolve().parents[1] / "tutorials" / "ep1" / "scenario.yaml"
    monkeypatch.setattr(SV, "work_dir", lambda p: tmp_path)
    data = "data:audio/webm;base64," + base64.b64encode(b"\x1a\x45\xdf\xa3" + b"0" * 5000).decode()
    assert SV.save_my_voice(ep1, "../../etc", data)["ok"] is False                # 장면 표에 없는 키
    assert SV.save_my_voice(ep1, "S1", "data:audio/webm;base64,AAAA")["ok"] is False  # 너무 짧음
    assert SV.save_my_voice(ep1, "S1", data)["ok"] and (tmp_path / "my_voice" / "S1.webm").exists()

"""클라우드 VM(GPU 없음) 방식: Whisper API 받아쓰기, 환경 변수(서비스 계정) 드라이브 연결, 폴더 찾기·영상 목록."""
import json
import re

import numpy as np
import pytest

from autoedit import gdrive, transcribe as tr


# ── 받아쓰기 (OpenAI Whisper API) ──

def test_segs_from_api_assigns_words_to_segments():
    resp = {"segments": [{"start": 0, "end": 2, "avg_logprob": -0.2}, {"start": 2, "end": 4, "avg_logprob": -0.5}],
            "words": [{"word": " 안녕", "start": 0.1, "end": 0.5}, {"word": "하세요", "start": 0.5, "end": 1.0},
                      {"word": "", "start": 1, "end": 1}, {"word": "어", "start": 2.2, "end": 2.4}]}
    segs = tr.segs_from_api(resp, offset=10)
    assert [[w.text for w in s.words] for s in segs] == [["안녕", "하세요"], ["어"]]
    assert segs[1].words[0].start == 12.2 and segs[0].logprob == -0.2


class FakeTranscriptions:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return FakeResp({"duration": 1.0, "segments": [{"start": 0.0, "end": 1.0, "avg_logprob": -0.1}],
                         "words": [{"word": f"말{len(self.calls)}", "start": 0.2, "end": 0.6}]})


class FakeResp:
    def __init__(self, d):
        self.d = d

    def model_dump(self):
        return self.d


class FakeClient:
    def __init__(self):
        self.audio = type("A", (), {})()
        self.audio.transcriptions = FakeTranscriptions()


def test_transcribe_api_splits_long_audio_and_offsets_time(monkeypatch):
    monkeypatch.setattr(tr, "API_CHUNK_SEC", 2)
    client = FakeClient()
    audio = np.zeros(16000 * 5, dtype=np.float32)        # 5초 → 2초씩 3조각
    words = tr.transcribe_api(audio, ["ko"], ["태권도"], log=lambda *_: None, client=client)
    calls = client.audio.transcriptions.calls
    assert len(calls) == 3 and calls[0]["model"] == "whisper-1" and calls[0]["language"] == "ko"
    assert "태권도" in calls[0]["prompt"] and calls[0]["timestamp_granularities"] == ["word", "segment"]
    assert [(w.text, w.start) for w in words] == [("말1", 0.2), ("말2", 2.2), ("말3", 4.2)]


def test_resolve_engine(monkeypatch):
    assert tr.resolve_engine("local") == "local" and tr.resolve_engine("openai") == "openai"
    monkeypatch.setattr(tr, "_has_cuda", lambda: False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert tr.resolve_engine("auto") == "local"           # 키 없으면 PC
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert tr.resolve_engine("auto") == "openai"          # GPU 없고 키 있음(VM) → API
    monkeypatch.setattr(tr, "_has_cuda", lambda: True)
    try:
        import faster_whisper  # noqa: F401
        assert tr.resolve_engine("auto") == "local"       # GPU 있으면 무료 PC 받아쓰기
    except ImportError:
        assert tr.resolve_engine("auto") == "openai"


# ── 드라이브 (환경 변수) ──

SA = {"type": "service_account", "client_email": "video-test@p.iam.gserviceaccount.com",
      "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"}


def test_parse_json_env_tolerates_wrapping():
    text = "," + json.dumps(SA) + ",\n"                  # 환경 변수 칸에 앞뒤 쉼표·줄바꿈을 붙인 경우
    assert gdrive.parse_json_env(text)["client_email"] == SA["client_email"]
    with pytest.raises(gdrive.DriveNotReady):
        gdrive.parse_json_env("not json")


def test_status_with_service_account(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(SA))
    assert gdrive.env_mode() == "service"
    assert SA["client_email"] in gdrive.status()


def test_env_oauth_mode(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"):
        monkeypatch.setenv(k, "v")
    assert gdrive.env_mode() == "oauth-env"
    assert gdrive.env_credentials().refresh_token == "v"


def test_folder_id_from():
    fid = "1Z_-gAUPGTMsHiv47PLsxcsX51yWwujhl"
    assert gdrive.folder_id_from(f"https://drive.google.com/drive/folders/{fid}?usp=sharing") == fid
    assert gdrive.folder_id_from(fid) == fid and gdrive.folder_id_from("Output") is None


class Resp:
    def __init__(self, body=None, code=200):
        self.status_code, self._body, self.headers = code, body or {}, {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class DriveTree:
    """이름·부모로 폴더를 찾는 가짜 드라이브."""
    def __init__(self):
        self.items = [{"id": "f_edit", "name": "영상 편집", "parent": None, "mimeType": gdrive.FOLDER_MIME},
                      {"id": "f_cs", "name": "Claude Success", "parent": "f_edit", "mimeType": gdrive.FOLDER_MIME},
                      {"id": "v1", "name": "강의.mp4", "parent": "f_cs", "mimeType": "video/mp4"},
                      {"id": "d1", "name": "메모.txt", "parent": "f_cs", "mimeType": "text/plain"},
                      {"id": "v2", "name": "녹화.MOV", "parent": "f_cs", "mimeType": "application/octet-stream"}]

    def get(self, url, params=None, stream=False):
        q = params.get("q", "")
        out = []
        for it in self.items:
            if "name = '" in q and it["name"] != q.split("name = '")[1].split("'")[0]:
                continue
            m = re.search(r"'([^']+)' in parents", q)
            if m and it["parent"] != m.group(1):
                continue
            if "mimeType = 'application/vnd.google-apps.folder'" in q and it["mimeType"] != gdrive.FOLDER_MIME:
                continue
            if "mimeType != 'application/vnd.google-apps.folder'" in q and it["mimeType"] == gdrive.FOLDER_MIME:
                continue
            out.append(it)
        return Resp({"files": out})


def test_find_folder_by_path_and_list_videos():
    d = DriveTree()
    f = gdrive.find_folder(d, "영상 편집/Claude Success")
    assert f["id"] == "f_cs"
    assert [v["name"] for v in gdrive.list_videos(d, f["id"])] == ["강의.mp4", "녹화.MOV"]


def test_find_folder_missing_tells_service_email(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(SA))
    with pytest.raises(gdrive.DriveNotReady, match="video-test@"):
        gdrive.find_folder(DriveTree(), "Output")


def test_service_account_needs_target(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(SA))
    (tmp_path / "report.md").write_text("x", encoding="utf-8")
    with pytest.raises(gdrive.DriveNotReady, match="--drive-out"):
        gdrive.upload_results(tmp_path, sess=DriveTree(), log=lambda *_: None)


def test_gdrive_alias_name(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GDRIVE_SERVICE_ACCOUNT_JSON", "'" + json.dumps(SA, indent=2) + "'")   # 여러 줄·작은따옴표
    assert gdrive.env_mode() == "service" and gdrive.service_email() == SA["client_email"]

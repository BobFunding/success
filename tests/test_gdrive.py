"""구글 드라이브 올리기: 가짜 세션으로 폴더 재사용·조각 올리기·링크 기록을 확인한다(실제 구글에 안 붙음)."""
import json

from autoedit import gdrive


class Resp:
    def __init__(self, code=200, body=None, headers=None):
        self.status_code, self._body, self.headers = code, body or {}, headers or {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeSession:
    def __init__(self):
        self.folders, self.puts, self.perms = {}, [], []

    def get(self, url, params=None):
        name = params["q"].split("name = '")[1].split("'")[0]
        f = self.folders.get(name)
        return Resp(body={"files": [f] if f else []})

    def post(self, url, params=None, json=None, headers=None):
        if url == gdrive.UPLOAD:
            return Resp(200, headers={"Location": "https://upload/session"})
        if url.endswith("/permissions"):
            self.perms.append(url)
            return Resp(200, {"id": "p"})
        f = {"id": f"id_{json['name']}", "name": json["name"], "webViewLink": f"https://drive/{json['name']}"}
        self.folders[json["name"]] = f
        return Resp(200, f)

    def put(self, url, data=None, headers=None):
        self.puts.append(headers.get("Content-Range"))
        total = int(headers["Content-Range"].split("/")[1])
        end = int(headers["Content-Range"].split("-")[1].split("/")[0])
        if end + 1 < total:
            return Resp(308, headers={"Range": f"bytes=0-{end}"})
        return Resp(200, {"id": "f1", "name": "x", "webViewLink": "https://drive/file"})


def test_upload_results_writes_links_and_reuses_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(gdrive, "CHUNK", 4)
    work = tmp_path / "영상_20261118"
    work.mkdir()
    (work / "3_shorts.mp4").write_bytes(b"0123456789")        # 4바이트씩 3조각
    (work / "report.md").write_text("리포트", encoding="utf-8")
    sess = FakeSession()
    r = gdrive.upload_results(work, sess=sess, log=lambda *_: None)
    assert r["folder"]["name"] == f"{gdrive.ROOT_NAME}/영상_20261118" and r["folder"]["link"]
    assert [f["name"] for f in r["files"]] == ["3_shorts.mp4", "report.md"]
    assert sess.puts[:3] == ["bytes 0-3/10", "bytes 4-7/10", "bytes 8-9/10"]
    assert json.loads((work / "drive.json").read_text(encoding="utf-8"))["shared_with_anyone"] is False
    assert sess.perms == []                                   # 기본은 나만 보기
    gdrive.upload_results(work, share_link=True, sess=sess, log=lambda *_: None)
    assert len(sess.folders) == 2 and len(sess.perms) == 1    # 같은 폴더 다시 씀, 공유 설정 1번


def test_status_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_FILE", str(tmp_path / "c.json"))
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "t.json"))
    assert gdrive.status().startswith("준비 안 됨")
    (tmp_path / "c.json").write_text("{}")
    assert gdrive.status().startswith("로그인 필요")
    (tmp_path / "t.json").write_text("{}")
    assert gdrive.status() == "연결됨"


def test_secrets_are_gitignored():
    from pathlib import Path
    ig = (Path(__file__).parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "google_client_secret.json" in ig and "google_token.json" in ig

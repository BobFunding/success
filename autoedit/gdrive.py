"""구글 드라이브 올리기: 편집 결과를 내 드라이브 폴더에 올리고 링크를 돌려준다(모바일에서 이어 보기).

- 로그인: OAuth(데스크톱 앱). 처음 한 번 브라우저에서 구글 계정으로 '허용'을 누르면,
  토큰을 이 PC 안(google_token.json)에만 저장하고 다음부터는 묻지 않는다. 저장소에는 절대 올리지 않는다(.gitignore).
- 권한: drive.file — 이 앱이 만든 파일·폴더만 다룬다. 내 드라이브의 다른 파일은 보지도 못한다.
- 준비(처음 한 번): 구글 클라우드에서 만든 OAuth 클라이언트(데스크톱 앱) 파일을
  프로젝트 폴더에 google_client_secret.json 이름으로 둔다. 순서는 README '구글 드라이브 연결' 절.
- 폴더: 내 드라이브 > 유튜브 자동 편집기 > <작업 폴더 이름>. 같은 작업을 다시 올리면 같은 폴더를 쓴다.
- 링크: 기본은 '나만 보기'(같은 구글 계정으로 로그인한 휴대폰에서 열림). 원하면 '링크가 있는 누구나 보기'.
"""
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

from .config import PROJECT_DIR

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_NAME = "유튜브 자동 편집기"
CHUNK = 8 * 1024 * 1024                     # 큰 영상은 8MB씩 나눠 올린다(끊겨도 그 조각만 다시)
# 올릴 결과물(있는 것만). 1_cut.mp4 는 중간본이라 올리지 않는다.
RESULT_FILES = ["2_final.mp4", "3_shorts.mp4", "subtitles.srt", "report.md"]


class DriveNotReady(RuntimeError):
    """클라이언트 파일이 없거나 로그인이 안 된 상태. 메시지에 해야 할 일을 쓴다."""


def client_file() -> Path:
    return Path(os.environ.get("GOOGLE_CLIENT_SECRET_FILE") or PROJECT_DIR / "google_client_secret.json")


def token_file() -> Path:
    return Path(os.environ.get("GOOGLE_TOKEN_FILE") or PROJECT_DIR / "google_token.json")


def status() -> str:
    """웹 화면에 보여 줄 연결 상태 한 줄."""
    if token_file().exists():
        return "연결됨"
    if client_file().exists():
        return "로그인 필요 (처음 한 번 '허용')"
    return "준비 안 됨: google_client_secret.json 이 없습니다 (README '구글 드라이브 연결' 참고)"


def credentials(interactive: bool = True, log=print):
    """저장된 토큰을 쓰고, 만료됐으면 새로 받는다. 없으면(interactive) 브라우저로 로그인한다."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    tok = token_file()
    creds = None
    if tok.exists():
        creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception as e:  # 토큰이 취소됐거나 만료 → 다시 로그인
            log(f"[드라이브] 저장된 로그인이 만료돼 다시 로그인합니다: {e}")
    if not interactive:
        raise DriveNotReady("구글 드라이브 로그인이 필요합니다. 웹 화면의 '드라이브에 올리기'를 한 번 눌러 '허용'해 주세요.")
    if not client_file().exists():
        raise DriveNotReady(f"{client_file().name} 이 없습니다. README '구글 드라이브 연결' 순서대로 받아 "
                            f"프로젝트 폴더에 두세요.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    log("[드라이브] 브라우저에서 구글 계정을 고르고 '허용'을 눌러 주세요.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file()), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True,
                                  success_message="태권월드 편집기: 구글 드라이브 연결이 끝났습니다. 이 창은 닫아도 됩니다.")
    _save_token(creds)
    return creds


def _save_token(creds) -> None:
    tok = token_file()
    tok.write_text(creds.to_json(), encoding="utf-8")
    try:
        tok.chmod(0o600)          # 이 PC 의 다른 사용자가 읽지 못하게
    except OSError:
        pass


def session(interactive: bool = True, log=print):
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(credentials(interactive, log))


def _check(r, what: str) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"{what} 실패 ({r.status_code}): {r.text[:300]}")
    return r.json() if r.content else {}


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def find_or_create_folder(sess, name: str, parent: str | None = None) -> dict:
    """이름이 같은 폴더가 있으면 그걸 쓰고, 없으면 만든다(이 앱이 만든 폴더만 보인다)."""
    q = f"name = '{_q(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    if parent:
        q += f" and '{parent}' in parents"
    found = _check(sess.get(f"{API}/files", params={"q": q, "fields": "files(id,name,webViewLink)",
                                                   "spaces": "drive", "pageSize": 1}), "폴더 찾기")
    if found.get("files"):
        return found["files"][0]
    meta = {"name": name, "mimeType": FOLDER_MIME, **({"parents": [parent]} if parent else {})}
    return _check(sess.post(f"{API}/files", params={"fields": "id,name,webViewLink"}, json=meta), "폴더 만들기")


def upload_file(sess, path: Path, parent: str, log=print) -> dict:
    """파일 하나를 이어 올리기(resumable) 방식으로 올린다. 같은 이름이 이미 있으면 새로 하나 더 만든다."""
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix == ".srt":
        mime = "text/plain"
    if path.suffix == ".md":
        mime = "text/markdown"
    start = sess.post(UPLOAD, params={"uploadType": "resumable", "fields": "id,name,webViewLink"},
                      json={"name": path.name, "parents": [parent]},
                      headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)})
    if start.status_code >= 400 or "Location" not in start.headers:
        raise RuntimeError(f"{path.name} 올리기 시작 실패 ({start.status_code}): {start.text[:300]}")
    url = start.headers["Location"]
    sent = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK)
            end = sent + len(chunk) - 1
            headers = {"Content-Length": str(len(chunk))}
            if size:
                headers["Content-Range"] = f"bytes {sent}-{end}/{size}"
            r = sess.put(url, data=chunk, headers=headers)
            if r.status_code in (200, 201):
                if size > CHUNK:
                    log(f"[드라이브] {path.name} 100%")
                return r.json()
            if r.status_code != 308:     # 308 = 이 조각 받았음, 다음 조각
                raise RuntimeError(f"{path.name} 올리기 실패 ({r.status_code}): {r.text[:300]}")
            rng = r.headers.get("Range")        # 서버가 실제로 받은 곳까지(예: bytes=0-8388607)
            sent = int(rng.split("-")[1]) + 1 if rng else end + 1
            f.seek(sent)
            log(f"[드라이브] {path.name} {sent * 100 // max(size, 1)}%")


def share_anyone(sess, file_id: str) -> None:
    _check(sess.post(f"{API}/files/{file_id}/permissions", json={"role": "reader", "type": "anyone"}),
           "링크 공유 설정")


def upload_results(work: Path, share_link: bool = False, sess=None, log=print) -> dict:
    """작업 폴더의 결과물을 드라이브에 올리고 링크를 drive.json 에 남긴다."""
    work = Path(work)
    files = [work / n for n in RESULT_FILES if (work / n).exists()]
    if not files:
        raise RuntimeError("올릴 결과물이 없습니다 (편집이 끝난 폴더인지 확인해 주세요).")
    sess = sess or session(log=log)
    root = find_or_create_folder(sess, ROOT_NAME)
    folder = find_or_create_folder(sess, work.name, root["id"])
    if share_link:
        share_anyone(sess, folder["id"])          # 폴더를 공유하면 안의 파일도 같이 열린다
    out = []
    for p in files:
        log(f"[드라이브] {p.name} 올리는 중 ({p.stat().st_size / 1e6:.1f}MB)")
        meta = upload_file(sess, p, folder["id"], log)
        out.append({"name": p.name, "id": meta.get("id"), "link": meta.get("webViewLink")})
    result = {"folder": {"name": f"{ROOT_NAME}/{work.name}", "id": folder["id"], "link": folder.get("webViewLink")},
              "shared_with_anyone": share_link, "files": out}
    (work / "drive.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[드라이브] 완료: {result['folder']['link']}")
    return result


def links_markdown(result: dict) -> str:
    """웹 화면·리포트에 보여 줄 링크 목록."""
    who = "링크가 있는 누구나 볼 수 있음" if result.get("shared_with_anyone") else "나만 보기 (같은 구글 계정으로 로그인한 휴대폰에서 열림)"
    lines = [f"**드라이브 폴더**: [{result['folder']['name']}]({result['folder']['link']})  ", f"공유: {who}", ""]
    lines += [f"- [{f['name']}]({f['link']})" for f in result["files"]]
    return "\n".join(lines)

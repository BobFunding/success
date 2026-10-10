"""튜토리얼 메이커 화면: PC 안에서만 열리는 웹 화면 + 작은 Python 서버 (DESIGN.md 3절).

- 127.0.0.1 에서만 듣고, 다른 주소(Host)로 들어온 요청은 받지 않는다.
- 오래 걸리는 일(한 번 해 보이기, 리허설, 만들기)은 작업 하나씩 뒤에서 돌리고, 화면은 /api/job 으로 진행 상황을 본다.
- 브라우저 조작(Playwright)은 그 작업을 시작한 스레드 안에서만 한다.
"""
from __future__ import annotations

import json
import mimetypes
import os
import platform
import subprocess
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from . import rules as R
from . import scenario as S

ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).parent / "web"
PROJECTS = ROOT / "output" / "tutorial"
EXAMPLE = ROOT / "tutorials" / "ep1" / "scenario.yaml"
VOICES = [  # (이름, 목소리, 기본 빠르기)
    ("현수 · 차분", "ko-KR-HyunsuMultilingualNeural", -8),
    ("선희 · 밝게", "ko-KR-SunHiNeural", 0),
    ("인준 · 또박또박", "ko-KR-InJoonNeural", -4),
]


def work_dir(scn: Path) -> Path:
    """장면 표가 작업 폴더 안에 있으면 그 폴더, 아니면(1편 예시 등) output/tutorial/<파일이름>."""
    scn = scn.resolve()
    if PROJECTS.resolve() in scn.parents:
        return scn.parent
    d = yaml.safe_load(scn.read_text(encoding="utf-8")) or {}
    return PROJECTS / str(d.get("파일이름") or scn.stem)


def allowed(p: Path) -> bool:
    p = p.resolve()
    return any(r in p.parents or p == r for r in (PROJECTS.resolve(), (ROOT / "tutorials").resolve(),
                                                  S.PRESETS.resolve(), S.USER_BRANDS.resolve()))


class Job:
    """뒤에서 도는 작업 하나 (한 번에 하나만)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state: dict = {"kind": "", "running": False}
        self.stop = threading.Event()

    def start(self, kind: str, fn, **info) -> bool:
        with self.lock:
            if self.state.get("running"):
                return False
            self.stop.clear()
            self.state = {"kind": kind, "running": True, "stage": "", "done": [], "log": [], "started": time.time(),
                          "est": {}, "stage_started": time.time(), **info}

        def run():
            try:
                res = fn(self)
                self.update(result=res, ok=True)
            except Exception as e:                    # 사람 말 오류는 그대로, 그 밖은 짧게
                from .recorder import SceneError
                msg = str(e) if isinstance(e, (SceneError, S.ScenarioError, ValueError, RuntimeError)) else \
                    f"예상하지 못한 오류가 났어요: {type(e).__name__}"
                self.update(ok=False, error=msg, trace=traceback.format_exc()[-3000:],
                            scene=getattr(getattr(e, "scene", None), "no", None))
            finally:
                self.update(running=False, finished=time.time())
        threading.Thread(target=run, daemon=True).start()
        return True

    def update(self, **kw):
        with self.lock:
            self.state.update(kw)

    def log(self, msg: str):
        with self.lock:
            self.state["log"] = (self.state.get("log", []) + [str(msg)])[-200:]

    def stage(self, name: str, est: dict | None = None):
        with self.lock:
            cur = self.state.get("stage")
            if cur and cur != name and cur not in self.state["done"]:
                self.state["done"].append(cur)
            self.state["stage"] = name
            self.state["stage_started"] = time.time()
            if est:
                self.state["est"] = est

    def view(self) -> dict:
        with self.lock:
            st = dict(self.state)
        if st.get("running") and st.get("est"):
            names = list(st["est"])
            left = 0.0
            for n in names:
                if n in st["done"]:
                    continue
                v = st["est"][n]
                if n == st.get("stage"):
                    v = max(v * 0.15, v - (time.time() - st["stage_started"]))
                left += v
            st["eta"] = round(left)
        st.pop("trace", None)
        return st


JOB = Job()
DEMO: dict = {}          # 한 번 해 보이기 중인 세션 정보 (작업 스레드가 채움)


# ── 화면에서 쓰는 일들 ──
def list_projects() -> list[dict]:
    out = []
    items = sorted(PROJECTS.glob("*/scenario.yaml"), key=lambda p: -p.stat().st_mtime) if PROJECTS.exists() else []
    for p in [EXAMPLE] + items:
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
            w = work_dir(p)
            vids = sorted(w.glob("*_1440p60.mp4"))
            out.append({"path": str(p), "title": str(d["제목"]).replace("[", "").replace("]", ""),
                        "scenes": len(d.get("장면") or []), "example": p == EXAMPLE, "video": str(vids[0]) if vids else "",
                        "updated": p.stat().st_mtime})
        except Exception:
            continue
    return out


def project_view(path: Path) -> dict:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    w = work_dir(path)
    reh = json.loads((w / "rehearsal.json").read_text(encoding="utf-8")) if (w / "rehearsal.json").exists() else None
    try:
        sc = S.load(path)
        warn = R.warnings(sc, R.merged(R.load_user(), sc.brand.rules, sc.rules))
        err = ""
    except S.ScenarioError as e:
        warn, err = [], str(e)
    choices = json.loads((w / "choices.json").read_text(encoding="utf-8")) if (w / "choices.json").exists() else {}
    pron = json.loads((w / "pronunciation.json").read_text(encoding="utf-8")) if (w / "pronunciation.json").exists() else None
    qa_res = json.loads((w / "qa.json").read_text(encoding="utf-8")) if (w / "qa.json").exists() else None
    vids = sorted(w.glob("*_1440p60.mp4"))
    files = [str(f) for pat in ("*_1440p60.mp4", "*_1080p30.mp4", "*.srt", "챕터.txt") for f in sorted(w.glob(pat))]
    chap = (w / "챕터.txt").read_text(encoding="utf-8").splitlines() if (w / "챕터.txt").exists() else []
    return {"path": str(path), "scenario": d, "files": files, "chapters": chap, "pronunciation": pron, "qa": qa_res, "rehearsal": reh, "warnings": warn, "error": err, "work": str(w),
            "choices": choices, "video": str(vids[0]) if vids else "", "example": path.resolve() == EXAMPLE.resolve()}


def save_project(path: Path, d: dict) -> Path:
    """화면에서 고친 장면 표 저장. 1편 예시는 원본을 지키고 작업 폴더에 사본으로 저장한다."""
    if path.resolve() == EXAMPLE.resolve():
        path = work_dir(path) / "scenario.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    from .demo_record import save
    save(d, path)
    S.load(path)                              # 잘못 고쳤으면 여기서 사람 말 오류
    return path


def scenario_with_choices(path: Path, ch: dict) -> S.Scenario:
    """선택 단계에서 고른 목소리·꾸미기를 이번 영상에 반영한 장면 표."""
    sc = S.load(path)
    if ch.get("brand") and ch.get("deco") != "basic" and ch["brand"] in S.brand_names():
        sc.brand = S.load_brand(ch["brand"])
    if ch.get("deco") == "basic":
        keep = sc.brand
        sc.brand = S.load_brand("basic")
        sc.brand.spoken, sc.brand.name = keep.spoken, keep.name   # 이름 표기는 그대로, 모양만 기본
    v = next((v for v in VOICES if v[0] == ch.get("voice")), None)
    if v:
        sc.brand.voice, sc.brand.voice_rate = v[1], v[2]
    sc.brand.voice_rate += int(ch.get("speed", 0))
    return sc


def job_demo(job: Job, url: str, topic: str, brand: str, tone: str, next_topic: str):
    from .demo_record import DemoSession, save
    headless = os.environ.get("TUTORIAL_HEADLESS") == "1"
    sess = DemoSession(url, headless=headless, cdp_port=int(os.environ.get("TUTORIAL_DEMO_CDP", "0")) or None)
    DEMO.clear(); DEMO.update(session=sess)
    job.stage("기록 중")
    while not job.stop.is_set():
        job.update(count=len(sess.events))
        try:
            sess.page.wait_for_timeout(300)        # 브라우저 일을 처리하면서 기다림
        except Exception:
            break                                  # 사람이 창을 닫음 = 끝
    job.update(count=len(sess.events))
    sc = sess.finish(topic=topic, brand=brand, tone=tone, next_topic=next_topic)
    path = PROJECTS / sc["파일이름"] / "scenario.yaml"
    save(sc, path)
    return {"path": str(path), "scenes": len(sc["장면"])}


def job_rehearse(job: Job, path: Path, ch: dict):
    from . import maker, qa
    sc = scenario_with_choices(path, ch)
    w = work_dir(path)
    job.stage("목소리 만들기")
    nar = maker.narrate(sc, w, job.log)
    job.stage("발음 검사")
    qa.pronunciation(sc, nar, w, log=job.log)
    job.stage("리허설")
    maker.rehearse(sc, w, {k: v[2] for k, v in nar.items()}, job.log)
    return {"ok": True}


def job_make(job: Job, path: Path, ch: dict, preview: bool = False):
    from . import maker
    sc = scenario_with_choices(path, ch)
    w = work_dir(path)
    (w / "choices.json").write_text(json.dumps(ch, ensure_ascii=False), encoding="utf-8")
    return maker.make(sc, w, log=job.log, on_stage=job.stage, subtitles=ch.get("subtitles", True), preview=preview)


def voice_preview(path: Path, voice_name: str, speed: int) -> str:
    from .. import narration as N
    sc = S.load(path)
    v = next((v for v in VOICES if v[0] == voice_name), VOICES[0])
    first = (sc.scenes[0].line if sc.scenes else sc.lines()[0])
    out = work_dir(path) / "preview"
    ln = N.Line(f"preview_{VOICES.index(v)}_{speed}", first.text, first.rate, first.pitch)
    wav = out / f"{ln.key}.wav"
    if not wav.exists():
        N.synthesize([ln], out.resolve(), voice=v[1], base_rate=v[2] + speed, log=lambda *a: None)
    return str(wav)


def brand_view(name: str) -> dict:
    p = S.brand_path(name)
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    b = S.load_brand(name)
    return {"name": name, "data": d, "logo": b.logo, "builtin": S.PRESETS in p.parents,
            "contrast": contrast_report(b)}


def save_brand(name: str, d: dict, logo_b64: str = "") -> str:
    import base64
    import re
    key = re.sub(r"[^\w가-힣-]+", "_", name).strip("_") or "brand"
    S.USER_BRANDS.mkdir(parents=True, exist_ok=True)
    if logo_b64:
        (S.USER_BRANDS / f"{key}_logo.png").write_bytes(base64.b64decode(logo_b64.split(",", 1)[-1]))
        d["로고"] = f"{key}_logo.png"
    elif d.get("로고") and not (S.USER_BRANDS / d["로고"]).exists():
        src = S.PRESETS / "brands" / d["로고"]         # 기본 제공 브랜드를 고쳐 저장: 로고도 같이 복사
        if src.exists():
            (S.USER_BRANDS / d["로고"]).write_bytes(src.read_bytes())
    (S.USER_BRANDS / f"{key}.yaml").write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return key


def _lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_report(b: S.Brand) -> dict:
    """읽힘 검사: 흰 제목·자막이 배경 위에서 읽히는지(4.5 이상), 단계 표시 흰 글자가 포인트색 위에서(3 이상)."""
    bg = min(contrast("#FFFFFF", c) for c in b.background)
    pt = contrast("#FFFFFF", b.point)
    msgs = []
    if bg < 4.5:
        msgs.append("배경색이 밝아서 흰 제목이 잘 안 읽혀요. 배경을 조금 어둡게 해 주세요.")
    if pt < 2.2:
        msgs.append("포인트색이 밝아서 단계 번호가 잘 안 보여요.")
    return {"ok": not msgs, "messages": msgs, "bg": round(bg, 1), "point": round(pt, 1)}


def open_folder(p: Path):
    p = p if p.is_dir() else p.parent
    if platform.system() == "Windows":
        os.startfile(str(p))                         # noqa
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)], stderr=subprocess.DEVNULL)


# ── HTTP ──
class Handler(BaseHTTPRequestHandler):
    server_version = "TutorialMaker"

    def log_message(self, *a):
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"", "text/plain")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/state":
                return self.json({"projects": list_projects(), "brands": S.brand_names(), "voices": [v[0] for v in VOICES],
                                  "rules": R.merged(R.load_user()), "default_rules": R.DEFAULT, "job": JOB.view(),
                                  "capture": __import__("autoedit.tutorial.capture", fromlist=["x"]).capture_method()})
            if u.path == "/api/project":
                return self.json(project_view(Path(q["path"])))
            if u.path == "/api/job":
                return self.json(JOB.view())
            if u.path == "/api/brand":
                return self.json(brand_view(q.get("name") or "taekwonworld"))
            if u.path == "/file":
                return self.file(Path(q["path"]))
            return self.static(u.path)
        except Exception as e:
            return self.json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"", "text/plain")
        u = urlparse(self.path)
        try:
            b = self.body()
            if u.path == "/api/demo/start":
                ok = JOB.start("demo", lambda j: job_demo(j, b["url"], b.get("topic", ""), b.get("brand", ""),
                                                          b.get("tone", ""), b.get("next", "")), count=0)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/demo/stop":
                JOB.stop.set()
                return self.json({"ok": True})
            if u.path == "/api/project/save":
                p = save_project(Path(b["path"]), b["scenario"])
                return self.json({"ok": True, "path": str(p)})
            if u.path == "/api/rehearse":
                ok = JOB.start("rehearse", lambda j: job_rehearse(j, Path(b["path"]), b.get("choices", {})), path=b["path"])
                return self.json({"ok": ok})
            if u.path == "/api/make":
                pv = bool(b.get("preview"))
                ok = JOB.start("make", lambda j: job_make(j, Path(b["path"]), b.get("choices", {}), pv), path=b["path"], preview=pv)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/voice":
                return self.json({"wav": voice_preview(Path(b["path"]), b.get("voice", ""), int(b.get("speed", 0)))})
            if u.path == "/api/brand/save":
                return self.json({"ok": True, "name": save_brand(b["name"], b["data"], b.get("logo", ""))})
            if u.path == "/api/rules/save":
                R.save_user(b["rules"])
                return self.json({"ok": True, "rules": R.merged(R.load_user())})
            if u.path == "/api/rules/reset":
                R.save_user({})
                return self.json({"ok": True, "rules": R.merged()})
            if u.path == "/api/open":
                open_folder(Path(b["path"]))
                return self.json({"ok": True})
            return self.json({"error": "없는 요청"}, 404)
        except S.ScenarioError as e:
            return self.json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            return self.json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    def static(self, path: str):
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"", "text/plain")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        return self._send(200, f.read_bytes(), ctype)

    def file(self, p: Path):
        """작업 폴더 파일(영상·소리·사진). 영상 넘겨 보기를 위해 Range 를 지원한다."""
        if not allowed(p) or not p.is_file():
            return self._send(404, b"", "text/plain")
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, z = rng[6:].partition("-")
            a = int(a or 0)
            z = min(int(z) if z else size - 1, a + 8 * 1024 * 1024 - 1, size - 1)
            with p.open("rb") as fh:
                fh.seek(a)
                data = fh.read(z - a + 1)
            return self._send(206, data, ctype, {"Content-Range": f"bytes {a}-{z}/{size}", "Accept-Ranges": "bytes"})
        return self._send(200, p.read_bytes(), ctype, {"Accept-Ranges": "bytes"})


def serve(port: int = 8770, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"튜토리얼 메이커가 열렸어요: {url}\n이 검은 창은 켜 두세요. 끄면 프로그램도 꺼집니다.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

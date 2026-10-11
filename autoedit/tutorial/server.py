"""튜토리얼 메이커 화면: PC 안에서만 열리는 웹 화면 + 작은 Python 서버 (DESIGN.md 3절).

- 127.0.0.1 에서만 듣고, 다른 주소(Host)로 들어온 요청은 받지 않는다.
- 오래 걸리는 일(한 번 해 보이기, 리허설, 만들기)은 작업 하나씩 뒤에서 돌리고, 화면은 /api/job 으로 진행 상황을 본다.
- 브라우저 조작(Playwright)은 그 작업을 시작한 스레드 안에서만 한다.
"""
from __future__ import annotations

import json
import re
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
from . import assistant as A  # AI 도우미(키 있을 때만)
from . import langs as LG      # 다국어
from . import ops as OPS       # 오류 보고·공유 파일·시리즈
from . import style as ST      # 참고 영상 스타일 카드
from . import voices as V      # 목소리 목록(AI·유료·내 목소리·자막만)은 voices.py


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

    def ask(self, question: str, shot: str = "", timeout: float = 900) -> str:
        """녹화 중에 사람에게 묻는다(인증번호 등). 화면에 질문이 뜨고, 답을 받을 때까지(최대 15분) 기다린다."""
        ev = threading.Event()
        with self.lock:
            self.state["ask"] = {"question": question, "shot": shot, "asked": time.time()}
            self._answer, self._ev = None, ev
        ev.wait(timeout)
        with self.lock:
            self.state.pop("ask", None)
            return self._answer or ""

    def answer(self, value: str) -> bool:
        with self.lock:
            ev = getattr(self, "_ev", None)
            self._answer = value
        if ev:
            ev.set()
        return bool(ev)

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
            mark = w / "작업중.json"
            out.append({"path": str(p), "title": str(d["제목"]).replace("[", "").replace("]", ""),
                        "scenes": len(d.get("장면") or []), "example": p == EXAMPLE, "video": str(vids[0]) if vids else "",
                        "updated": p.stat().st_mtime, "series": d.get("시리즈", ""), "no": d.get("편", ""),
                        "interrupted": json.loads(mark.read_text(encoding="utf-8")) if mark.exists() and not JOB.view().get("running") else None})
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
        warn, err, sc = [], str(e), None
    choices = json.loads((w / "choices.json").read_text(encoding="utf-8")) if (w / "choices.json").exists() else {}
    pron = json.loads((w / "pronunciation.json").read_text(encoding="utf-8")) if (w / "pronunciation.json").exists() else None
    qa_res = json.loads((w / "qa.json").read_text(encoding="utf-8")) if (w / "qa.json").exists() else None
    from . import secrets as SEC
    secrets_needed = SEC.needed(sc) if sc else []
    vids = sorted(w.glob("*_1440p60.mp4"))
    files = [str(f) for pat in ("*_1440p60.mp4", "*_1080p30.mp4", "*.srt", "챕터.txt") for f in sorted(w.glob(pat))]
    chap = (w / "챕터.txt").read_text(encoding="utf-8").splitlines() if (w / "챕터.txt").exists() else []
    ser = OPS.series_list(sorted(PROJECTS.glob("*/scenario.yaml")) if PROJECTS.exists() else [])
    exp = w / "내보내기" / "점검.json"
    export = json.loads(exp.read_text(encoding="utf-8")) if exp.exists() else None
    return {"path": str(path), "scenario": d, "files": files, "chapters": chap, "pronunciation": pron, "qa": qa_res, "secrets": secrets_needed, "rehearsal": reh, "warnings": warn, "error": err, "work": str(w),
            "choices": choices, "export": export,
            "series": {"name": d.get("시리즈", ""), "no": d.get("편", ""), "eps": ser.get(d.get("시리즈", ""), []), "names": sorted(ser)},
            "lines": [{"key": l.key, "text": l.text} for l in sc.lines()] if sc else [],
            "lang_source": LG.source(sc) if sc else {},
            "translations": LG.load(w),
            "langs": LG.LANGS,
            "ai_cost": {"translate": A.estimate("translate", len(sc.lines()))["text"]} if sc else {},
            "my_voice": [l.key for l in sc.lines() if not V.my_voice_missing([l], w)] if sc else [], "platforms": platforms_view(), "video": str(vids[0]) if vids else "", "example": path.resolve() == EXAMPLE.resolve()}


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
    v = V.find(ch.get("voice", ""))
    if v:
        sc.brand.voice, sc.brand.voice_rate = v["voice"], v["rate"]
    card = ST.get(ch["style"]) if ch.get("style") else None
    if card:                                       # 참고 영상 스타일: 편집 기법만(쉼·확대·말 빠르기)
        sc.style_rules = card["적용"]["rules"]
        if not int(ch.get("speed", 0)):
            sc.brand.voice_rate += int(card["적용"].get("speed", 0))
    sc.brand.voice_rate += int(ch.get("speed", 0))
    return sc


def job_demo(job: Job, url: str, topic: str, brand: str, tone: str, next_topic: str, purpose: str = "고객 안내"):
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
    sc = sess.finish(topic=topic, brand=brand, tone=tone, next_topic=next_topic, purpose=purpose)
    path = PROJECTS / sc["파일이름"] / "scenario.yaml"
    save(sc, path)
    return {"path": str(path), "scenes": len(sc["장면"])}


def job_ai(job: Job, url: str, goal: str, brand: str, tone: str, purpose: str = "고객 안내"):
    """AI에게 맡기기: AI가 사람 대신 한 번 해 보이고, 시연 때와 같은 방식으로 장면 표를 만든다."""
    from . import assistant as A
    from .demo_record import save
    llm = A.get_llm()
    job.stage("AI가 사이트를 둘러보는 중")
    r = A.explore(llm, url, goal, ask=job.ask, log=job.log, stop=job.stop.is_set, tone=tone, brand=brand, purpose=purpose,
                  headless=os.environ.get("TUTORIAL_HEADLESS", "1") == "1")
    sc = r["scenario"]
    path = PROJECTS / sc["파일이름"] / "scenario.yaml"
    save(sc, path)
    job.log(f"[AI] {r['steps']}번 조작, 어림 비용 {r['cost']}")
    return {"path": str(path), "scenes": len(sc["장면"]), "cost": r["cost"]}


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


def job_make(job: Job, path: Path, ch: dict, preview: bool = False, allow_real: bool = False):
    """만들기. 시작할 때 작업 폴더에 '작업중.json' 을 남기고 끝나면 지운다 — 컴퓨터가 꺼지거나 창을 닫아 중간에 멈추면
    다음에 열 때 [이어서 만들기]가 보인다(목소리·녹화·조각은 만들어 둔 것을 다시 쓰므로 남은 곳부터)."""
    mark = work_dir(path) / "작업중.json"
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(json.dumps({"choices": {k: v for k, v in ch.items() if k != "allow_real"}, "preview": preview,
                                "started": time.time()}, ensure_ascii=False), encoding="utf-8")
    try:
        return _job_make(job, path, ch, preview, allow_real)
    finally:
        mark.unlink(missing_ok=True)


def job_style(job: Job, src: Path, name: str):
    """참고 영상 → 스타일 카드. 원본은 분석이 끝나면 지운다(카드에는 숫자만)."""
    job.stage("참고 영상 분석 중")
    try:
        card = ST.analyze(src, name, log=job.log)
        p = ST.save(card)
    finally:
        src.unlink(missing_ok=True)
    return {"key": p.stem, "card": card}


def job_batch(job: Job, items: list[dict]):
    """여러 편 한꺼번에: 순서대로 만든다. 한 편이 멈춰도 다음 편으로(끝에 편마다 결과)."""
    out = []
    for i, it in enumerate(items):
        p = Path(it["path"])
        title = S.load(p).title_plain
        job.update(batch={"i": i + 1, "n": len(items), "title": title})
        job.log(f"[일괄] {i + 1}/{len(items)} {title}")
        try:
            cj = work_dir(p) / "choices.json"            # 지난번에 고른 목소리·꾸미기를 그대로
            ch = it.get("choices") or (json.loads(cj.read_text(encoding="utf-8")) if cj.exists() else {})
            r = job_make(job, p, ch)
            out.append({"path": str(p), "title": title, "ok": True, "final": r.get("final", "")})
        except Exception as e:
            job.log(f"[일괄] {title}: 멈춤 — {e}")
            out.append({"path": str(p), "title": title, "ok": False, "error": str(e)})
    return {"batch": out}


def update_check() -> dict:
    """새 버전 알림: 이 폴더가 git 으로 받은 것이면 원격과 비교한다(15초 안에 안 되면 조용히 넘어감)."""
    root = ROOT
    if not (root / ".git").exists():
        return {"ok": False, "how": "zip 으로 받은 폴더예요. 새 버전은 GitHub 에서 다시 받아 주세요."}
    try:
        br = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        subprocess.run(["git", "-C", str(root), "fetch", "-q", "origin", br], capture_output=True, timeout=15)
        n = subprocess.run(["git", "-C", str(root), "rev-list", "--count", f"HEAD..origin/{br}"], capture_output=True, text=True, timeout=5).stdout.strip()
        return {"ok": True, "behind": int(n or 0), "branch": br}
    except Exception as e:
        return {"ok": False, "how": f"확인하지 못했어요({type(e).__name__})."}


def update_apply() -> dict:
    """버튼 하나로 업데이트: 내 작업(output/·보관함·브랜드)은 그대로 두고 프로그램만 받는다(내가 고친 프로그램 파일이 있으면 멈춤)."""
    r = subprocess.run(["git", "-C", str(ROOT), "pull", "--ff-only", "-q"], capture_output=True, text=True, timeout=120)
    if r.returncode:
        return {"ok": False, "error": "업데이트하지 못했어요. 프로그램 파일을 직접 고쳤다면 개발자에게 물어봐 주세요.\n" + r.stderr[-300:]}
    return {"ok": True, "msg": "업데이트했어요. 창을 닫고 프로그램을 다시 켜 주세요."}


def _job_make(job: Job, path: Path, ch: dict, preview: bool = False, allow_real: bool = False):
    from . import maker
    from . import secrets as SEC
    sc = scenario_with_choices(path, ch)
    missing = [n["칸"] for n in SEC.needed(sc) if not n["있음"]]
    if missing:
        raise ValueError(f"비밀번호가 보관함에 없어요: {', '.join(missing)}. 확인 단계에서 한 번 적어 주세요.")
    w = work_dir(path)
    (w / "choices.json").write_text(json.dumps({k: v for k, v in ch.items() if k != "allow_real"}, ensure_ascii=False),
                                    encoding="utf-8")
    return maker.make(sc, w, log=job.log, on_stage=job.stage, subtitles=ch.get("subtitles", True), preview=preview,
                      ask=job.ask, allow_real=allow_real and not preview)


def job_export(job: Job, path: Path, dests: list[str], ch: dict, vertical: str = "따라가기"):
    from .export import Exporter
    sc = scenario_with_choices(path, ch)
    return Exporter(sc, work_dir(path), log=job.log, vertical=vertical).export(dests, on_stage=job.stage)


def platforms_view() -> list[dict]:
    from .export import load_platforms
    return [{"key": k, "name": p["이름"], "desc": p.get("설명", ""), "default": bool(p.get("기본"))}
            for k, p in load_platforms()["올릴곳"].items()]


KEYS = {"openai": "openai.com|api_key", "anthropic": "anthropic.com|api_key"}   # 보관함 열쇠


def keys_view() -> dict:
    from . import secrets as SEC
    env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    return {k: bool(os.environ.get(env[k]) or SEC.get(v)) for k, v in KEYS.items()}


def save_my_voice(path: Path, key: str, data: str) -> dict:
    """화면에서 녹음한 한 문장을 작업 폴더 my_voice/<키>.webm 으로. 키는 장면 표에 있는 것만."""
    import base64
    sc = S.load(path)
    if key not in {l.key for l in sc.lines()}:
        return {"ok": False, "error": "없는 문장이에요."}
    raw = base64.b64decode(data.split(",", 1)[-1])
    if len(raw) < 2000:
        return {"ok": False, "error": "녹음이 너무 짧아요. [● 녹음]을 누르고 문장을 읽은 뒤 [■ 멈춤]을 눌러 주세요."}
    d = V.my_voice_dir(work_dir(path))
    d.mkdir(parents=True, exist_ok=True)
    for e in (".webm", ".wav", ".ogg", ".m4a"):
        (d / f"{key}{e}").unlink(missing_ok=True)
    ext = ".ogg" if data.startswith("data:audio/ogg") else ".m4a" if "mp4" in data[:40] else ".webm"
    (d / f"{key}{ext}").write_bytes(raw)
    return {"ok": True}


def voice_preview(path: Path, voice_name: str, speed: int) -> str:
    """실제 첫 문장을 그 목소리로. 자막만이면 소리 없음(''), 내 목소리는 녹음한 첫 문장."""
    from .. import narration as N
    sc = S.load(path)
    v = V.find(voice_name) or V.choices()[0]
    first = (sc.scenes[0] if sc.scenes else sc.lines()[0])
    line = first.line if sc.scenes else first
    if v["voice"] == V.SILENT:
        return ""
    w = work_dir(path)
    out = w / "preview"
    if v["voice"] == V.MINE:
        if V.my_voice_missing([line], w):
            return ""
        ln = N.Line(line.key, line.text)
        V.mine([ln], w, out.resolve())
        return ln.path
    tag = re.sub(r"[^\w]", "_", v["voice"])
    ln = N.Line(f"preview_{tag}_{speed}", line.text, line.rate, line.pitch)
    wav = out / f"{ln.key}.wav"
    if not wav.exists():
        V.synthesize([ln], w, out.resolve(), v["voice"], v["rate"] + speed, log=lambda *a: None)
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
                return self.json({"projects": list_projects(), "brands": S.brand_names(), "voices": [v["name"] for v in V.choices()], "voice_list": V.choices(), "keys": keys_view(), "styles": ST.cards(), "ai_cost": A.estimate("explore")["text"],
                                  "rules": R.merged(R.load_user()), "default_rules": R.DEFAULT, "job": JOB.view(),
                                  "capture": __import__("autoedit.tutorial.capture", fromlist=["x"]).capture_method()})
            if u.path == "/api/project":
                return self.json(project_view(Path(q["path"])))
            if u.path == "/api/job":
                return self.json(JOB.view())
            if u.path == "/api/myvoice/file":
                d = V.my_voice_dir(work_dir(Path(q["path"])))
                f = next((d / f"{q['key']}{e}" for e in (".webm", ".wav", ".ogg", ".m4a") if (d / f"{q['key']}{e}").exists()), None)
                return self.json({"file": str(f) if f else ""})
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
            if u.path == "/api/style/upload":           # 참고 영상 파일: 그대로 받아 임시 폴더에(큰 파일이라 JSON 이 아님)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n < 4 * 1024 ** 3:
                    return self.json({"ok": False, "error": "영상 파일을 받지 못했어요(4GB 이하)."})
                src = ST.STYLES / "src" / f"upload{Path(q.get('file', 'v.mp4')).suffix[:6] or '.mp4'}"
                src.parent.mkdir(parents=True, exist_ok=True)
                with src.open("wb") as fh:
                    left = n
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        fh.write(chunk); left -= len(chunk)
                name = q.get("name") or Path(q.get("file", "참고 영상")).stem
                ok = JOB.start("style", lambda j: job_style(j, src, name), count=0)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            b = self.body()
            if u.path == "/api/style/delete":
                (ST.STYLES / f"{Path(str(b.get('key', ''))).name}.json").unlink(missing_ok=True)
                return self.json({"ok": True, "styles": ST.cards()})
            if u.path == "/api/demo/start":
                ok = JOB.start("demo", lambda j: job_demo(j, b["url"], b.get("topic", ""), b.get("brand", ""),
                                                          b.get("tone", ""), b.get("next", ""), b.get("purpose", "고객 안내")), count=0)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/batch":
                items = [x for x in b.get("items", []) if isinstance(x, dict) and x.get("path")]
                if not items:
                    return self.json({"ok": False, "error": "만들 작업을 하나 이상 골라 주세요."})
                ok = JOB.start("batch", lambda j: job_batch(j, items), count=0)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/update/check":
                return self.json(update_check())
            if u.path == "/api/update/apply":
                return self.json(update_apply())
            if u.path == "/api/report":
                pth = Path(b["path"]) if b.get("path") else None
                return self.json({"ok": True, "text": OPS.report(JOB.view(), pth if pth and allowed(pth) else None)})
            if u.path == "/api/project/pack":
                p = Path(b["path"])
                return self.json({"ok": True, "file": str(OPS.pack(p, work_dir(p)))})
            if u.path == "/api/project/unpack":
                import base64
                try:
                    np_ = OPS.unpack(base64.b64decode(str(b["data"]).split(",", 1)[-1]), PROJECTS)
                except (ValueError, __import__("zipfile").BadZipFile) as e:
                    return self.json({"ok": False, "error": str(e) or "공유 파일을 열지 못했어요."})
                return self.json({"ok": True, "path": str(np_)})
            if u.path == "/api/series":
                p = Path(b["path"])
                if p.resolve() == EXAMPLE.resolve():
                    p = save_project(p, yaml.safe_load(p.read_text(encoding="utf-8")))
                n = OPS.set_series(p, str(b.get("name", "")).strip(), int(b.get("no") or 1),
                                   sorted(PROJECTS.glob("*/scenario.yaml")))
                return self.json({"ok": True, "path": str(p), "changed": n})
            if u.path == "/api/ai/start":
                if not A.ensure_key():
                    return self.json({"ok": False, "need_key": True, "error": "AI 도우미 키가 없어요."})
                goal = str(b.get("goal", "")).strip()
                if not goal:
                    return self.json({"ok": False, "error": "무엇을 하는 방법인지 한 줄로 적어 주세요. 예: 관장님이 회원가입하는 방법"})
                ok = JOB.start("ai", lambda j: job_ai(j, b["url"], goal, b.get("brand", ""), b.get("tone", ""), b.get("purpose", "고객 안내")), count=0)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path in ("/api/translate", "/api/polish"):
                p = Path(b["path"])
                sc = S.load(p)
                try:
                    llm = A.get_llm()
                except A.LLMUnavailable as e:
                    return self.json({"ok": False, "need_key": True, "error": str(e)})
                if u.path == "/api/polish":
                    lines = {s_.key: s_.line.text for s_ in sc.scenes}
                    return self.json({"ok": True, "suggest": A.polish(llm, lines, sc.brand.tone, sc.brand.name)})
                lang = str(b.get("lang", ""))
                items = A.translate(llm, LG.source(sc), lang, sc.brand.name)
                LG.save(work_dir(p), lang, items)
                return self.json({"ok": True, "items": items})
            if u.path == "/api/translations/save":
                d = LG.save(work_dir(Path(b["path"])), str(b.get("lang", "")), dict(b.get("items") or {}))
                return self.json({"ok": True, "translations": d})
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
                pv, real = bool(b.get("preview")), bool(b.get("allow_real"))   # 실제 저장은 화면에서 매번 확인받은 경우만
                ok = JOB.start("make", lambda j: job_make(j, Path(b["path"]), b.get("choices", {}), pv, real),
                               path=b["path"], preview=pv)
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/export":
                dests = [d for d in b.get("to", []) if isinstance(d, str)]
                if not dests:
                    return self.json({"ok": False, "error": "올릴 곳을 하나 이상 골라 주세요."})
                ok = JOB.start("export", lambda j: job_export(j, Path(b["path"]), dests, b.get("choices", {}),
                                                                 "전체" if b.get("vertical") == "전체" else "따라가기"), path=b["path"])
                return self.json({"ok": ok} if ok else {"ok": False, "error": "다른 작업이 진행 중이에요."})
            if u.path == "/api/key":
                from . import secrets as SEC
                name, val = str(b.get("name", "")), str(b.get("value", "")).strip()
                if name not in KEYS or len(val) < 20:
                    return self.json({"ok": False, "error": "키 모양이 아니에요. 키 받는 곳에서 복사한 값을 그대로 붙여 넣어 주세요."})
                return self.json({"ok": True, "where": SEC.put(KEYS[name], val)})
            if u.path == "/api/myvoice":
                return self.json(save_my_voice(Path(b["path"]), str(b["key"]), str(b["data"])))
            if u.path == "/api/answer":
                return self.json({"ok": JOB.answer(str(b.get("value", "")))})
            if u.path == "/api/secret":
                from . import secrets as SEC
                return self.json({"ok": True, "where": SEC.put(b["key"], b["value"])})
            if u.path == "/api/project/startstate":
                from .demo_record import set_start_state
                p = Path(b["path"])
                d = set_start_state(yaml.safe_load(p.read_text(encoding="utf-8")), b["state"])
                np_ = save_project(p, d)
                return self.json({"ok": True, "path": str(np_)})
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

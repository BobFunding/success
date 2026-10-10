"""1편 재현 검사 (DESIGN.md 0절 완료 판정).

원래 1편 코드(tutorials/ep1/record_ep1.py, build_ep1.py)와 새 엔진(장면 표 tutorials/ep1/scenario.yaml)으로
1편을 만들어 비교한다. 같은 목소리 파일을 함께 쓴다.

1. 기준     : 원래 코드로 녹화 + 편집                         → <work>/base
2. 같은녹화 : 기준 녹화를 새 엔진으로 편집                     → <work>/same   (편집 부분이 똑같은지: 글자·길이·프레임 일치)
3. 프로그램 : 새 엔진으로 녹화 + 편집                         → <work>/engine (전체가 같은지: 클릭 위치 일치, 시각·길이는 허용 오차 안)

사이트를 실제로 조작하며 실시간으로 찍으므로 녹화끼리는 페이지 로딩 시간만큼 시각이 조금 다를 수 있다(허용 오차).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from ..ffmpeg_utils import FFMPEG, FFPROBE
from . import maker, scenario
from .capture import find_sync
from .compose import Composer

ROOT = Path(__file__).resolve().parents[2]
EP1 = ROOT / "tutorials" / "ep1"
TOL_T = 0.25            # 장면 안 박자 허용 오차(초)의 최소값: 장면마다 그 문장 시작부터 잰 시각
# 실제 허용치 = max(TOL_T, 원래 코드끼리의 흔들림). 원래 코드로 프로그램 녹화 앞뒤에 한 번씩 찍어 잰다
# (2026-10-10 사용자 결정: 원래 코드끼리도 F3·F8 이 0.26초까지 흔들려 고정 0.25초는 컴퓨터에 따라 너무 좁음)
TOL_XY = 1.5            # 클릭 위치 허용 오차(화면 픽셀, 2880x1620 기준)
TOL_LEN = 0.3           # 길이 허용 오차(초)


def _py(args, cwd):
    subprocess.run([sys.executable, *args], cwd=cwd, check=True)


def stage_base(work: Path, sc) -> None:
    """원래 1편 코드를 고치지 않고 그대로 돌린다(입력 파일만 넣어 줌)."""
    base = work / "base"
    base.mkdir(parents=True, exist_ok=True)
    for f in ("record_ep1.py", "build_ep1.py"):
        shutil.copy(EP1 / f, base / f)
    shutil.copy(work / "engine" / "narration.json", base / "narration.json")
    shutil.copy(sc.brand.logo, base / "logo.png")
    # 기준 녹화는 매번 새로 찍는다: 컴퓨터 빠르기가 때마다 달라서(목록 고르기처럼 조작이 문장보다 긴 장면이 밀림),
    # 몇 시간 전에 찍은 기준과 비교하면 엔진이 같아도 시각이 0.3초쯤 어긋난다(2026-10-10 실측)
    for f in ("cap.mkv", "log_rec.json", "sync.json", "body.mp4", "body_src.mp4"):
        (base / f).unlink(missing_ok=True)
    _py(["record_ep1.py", "rec"], base)
    log = json.loads((base / "log_rec.json").read_text(encoding="utf-8"))
    (base / "sync.json").write_text(json.dumps({"offset": find_sync(base / "cap.mkv", log["marks"]["sync"])}))


def build_base(work: Path) -> None:
    _py(["build_ep1.py"], work / "base")


def stage_same(work: Path, sc) -> None:
    same = work / "same"
    same.mkdir(parents=True, exist_ok=True)
    for f in ("narration.json", "log_rec.json", "sync.json"):
        shutil.copy(work / "base" / f, same / f)
    for f in ("body.mp4", "body.mp4.key", "body_src.mp4"):        # 기준 녹화가 새로 찍혔으므로 본편을 다시
        (same / f).unlink(missing_ok=True)
    if not (same / "cap.mkv").exists():
        (same / "cap.mkv").symlink_to((work / "base" / "cap.mkv").resolve())
    Composer(sc, same).build()


def stage_engine(work: Path, sc, stages=maker.STAGES) -> None:
    from .rules import merged
    maker.make(sc, work / "engine", stages=stages, rules=merged(), check=False)   # 사용자가 바꾼 규칙과 무관하게 1편 기본 규칙으로


# ── 비교 ──
def duration(p: Path) -> dict:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,duration,width,height,r_frame_rate",
                          "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"]
    v = next(s for s in st if s["codec_type"] == "video")
    a = next((s for s in st if s["codec_type"] == "audio"), {})
    return {"video": float(v["duration"]), "audio": float(a.get("duration", 0)), "size": f"{v['width']}x{v['height']}",
            "fps": v["r_frame_rate"]}


def frame(p: Path, t: float) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 0.0
    m = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    return 99.0 if m == 0 else float(10 * np.log10(255 ** 2 / m))


def _per_scene(log: dict) -> list[list[tuple]]:
    """장면(문장)마다 그 문장이 시작된 때부터 잰 클릭·밝게 하기 시각."""
    lines = [ln["t"] for ln in log["lines"]] + [float("inf")]
    out = []
    for i in range(len(lines) - 1):
        a, z = lines[i], lines[i + 1]
        cl = [("c", round(c["t"] - a, 3), c["x"], c["y"]) for c in log["clicks"] if a <= c["t"] < z]
        sp = [("s", round(s["start"] - a, 3), round(s["end"] - a, 3), s["x"], s["y"], s["w"], s["h"])
              for s in log["spots"] if a <= s["start"] < z]
        out.append(cl + sp)
    return out


def compare_logs(a: dict, b: dict, tol_t: float = TOL_T) -> dict:
    """녹화 기록 비교.
    - 위치: 클릭·밝게 하기 자리가 같아야 한다(0px 에 가깝게).
    - 박자: 장면마다 그 문장이 시작된 때부터 잰 시각이 같아야 한다(허용 TOL_T).
    - 밀림(정보): 영상 시작부터 잰 시각 차이. 사이트 로딩·컴퓨터 빠르기를 타는 장면(누른 뒤 화면 기다리기, 문장보다
      긴 조작)이 있으면 원래 코드끼리도 0.5초쯤 밀린다(2026-10-10 실측) — 판정에 쓰지 않는다."""
    a0, b0 = a["marks"]["body_start"], b["marks"]["body_start"]
    res = {"clicks": [len(a["clicks"]), len(b["clicks"])], "spots": [len(a["spots"]), len(b["spots"])],
           "lines": [[x["key"] for x in a["lines"]] == [x["key"] for x in b["lines"]]]}
    dxy = [max(abs(x["x"] - y["x"]), abs(x["y"] - y["y"])) for x, y in zip(a["clicks"], b["clicks"])]
    dbox = [max(abs(x[k] - y[k]) for k in ("x", "y", "w", "h")) for x, y in zip(a["spots"], b["spots"])]
    pa, pb = _per_scene(a), _per_scene(b)
    same_count = [len(x) for x in pa] == [len(y) for y in pb]
    rel = [abs(e[1] - f[1]) for x, y in zip(pa, pb) for e, f in zip(x, y)] + \
          [abs(e[2] - f[2]) for x, y in zip(pa, pb) for e, f in zip(x, y) if e[0] == "s"]
    drift = [abs((x["t"] - a0) - (y["t"] - b0)) for x, y in zip(a["lines"], b["lines"])]
    res.update(click_xy=max(dxy), spot_box=max(dbox), scene_events=same_count, scene_t=round(max(rel), 3),
               drift=round(max(drift), 3))
    res["ok"] = (res["clicks"][0] == res["clicks"][1] and res["spots"][0] == res["spots"][1] and res["lines"][0]
                 and same_count and res["click_xy"] <= TOL_XY and res["spot_box"] <= TOL_XY and res["scene_t"] <= tol_t)
    res["tol_t"] = round(tol_t, 3)
    return res


def srt_cues(p: Path) -> list[tuple[float, float, str]]:
    def sec(s):
        h, m, r = s.split(":"); s_, ms = r.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s_) + int(ms) / 1000
    out, blocks = [], p.read_text(encoding="utf-8").strip().split("\n\n")
    for b in blocks:
        ln = b.split("\n")
        a, z = ln[1].split(" --> ")
        out.append((sec(a), sec(z), ln[2]))
    return out


def compare_outputs(a: Path, b: Path, base: str, exact: bool, drift: float = 0.0) -> dict:
    fa, fb = a / f"{base}_1440p60.mp4", b / f"{base}_1440p60.mp4"
    da, db = duration(fa), duration(fb)
    ca, cb = srt_cues(a / f"{base}.srt"), srt_cues(b / f"{base}.srt")
    cue_t = max(max(abs(x[0] - y[0]), abs(x[1] - y[1])) for x, y in zip(ca, cb)) if len(ca) == len(cb) else 99
    chap_a = (a / "챕터.txt").read_text(encoding="utf-8").splitlines()
    chap_b = (b / "챕터.txt").read_text(encoding="utf-8").splitlines()
    res = {"len": [round(da["video"], 3), round(db["video"], 3)], "audio": [round(da["audio"], 3), round(db["audio"], 3)],
           "format": [f"{da['size']}@{da['fps']}", f"{db['size']}@{db['fps']}"],
           "srt_text": [c[2] for c in ca] == [c[2] for c in cb], "srt_t": round(cue_t, 3),
           "chapters": chap_a == chap_b, "chapters_a": chap_a, "chapters_b": chap_b}
    # 같은 시각의 프레임: 인트로·아웃트로(녹화와 무관)와 본편 여러 곳
    total = min(da["video"], db["video"])
    times = [1.0, 5.0, 9.0] + [total * f for f in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)] + [total - 6, total - 1.5]
    res["frames"] = [(round(t, 2), round(psnr(frame(fa, t), frame(fb, t)), 1)) for t in times]
    if exact:
        ass = lambda d: next(p for p in (d / f"{base}.ass", d / "ep1.ass") if p.exists())   # 원래 코드는 ep1.ass
        res["ass"] = ass(a).read_text(encoding="utf-8") == ass(b).read_text(encoding="utf-8")
        res["srt"] = (a / f"{base}.srt").read_text(encoding="utf-8") == (b / f"{base}.srt").read_text(encoding="utf-8")
        res["ok"] = (res["ass"] and res["srt"] and res["chapters"] and res["len"][0] == res["len"][1]
                     and all(q >= 99 for _, q in res["frames"]))
    else:
        # 녹화가 밀린 만큼은 길이·자막·챕터 시각에도 그대로 나타난다
        names = lambda ch: [c.split(" ", 1)[1] for c in ch]
        secs = lambda ch: [int(c.split(" ")[0].split(":")[0]) * 60 + int(c.split(" ")[0].split(":")[1]) for c in ch]
        res["chapters"] = names(chap_a) == names(chap_b) and all(abs(x - y) <= 1 + drift for x, y in zip(secs(chap_a), secs(chap_b)))
        res["ok"] = (res["srt_text"] and res["srt_t"] <= TOL_T + drift and abs(res["len"][0] - res["len"][1]) <= TOL_LEN + drift
                     and res["format"][0] == res["format"][1] and res["chapters"] and all(q >= 99 for t, q in res["frames"][:3]))
    return res


def report(work: Path, sc) -> bool:
    base = sc.file_name
    base_log = json.loads((work / "base" / "log_rec.json").read_text(encoding="utf-8"))
    pre = work / "base" / "log_rec_pre.json"
    noise = None
    if pre.exists():                                     # 원래 코드끼리의 흔들림 = 이번 허용치
        noise = compare_logs(json.loads(pre.read_text(encoding="utf-8")), base_log, tol_t=99)
    tol = max(TOL_T, noise["scene_t"]) if noise else TOL_T
    rec = compare_logs(base_log, json.loads((work / "engine" / "log_rec.json").read_text(encoding="utf-8")), tol_t=tol)
    if noise:
        rec["원래코드끼리"] = {k: noise[k] for k in ("scene_t", "click_xy", "spot_box", "drift")}
    same = compare_outputs(work / "base", work / "same", base, exact=True)
    eng = compare_outputs(work / "base", work / "engine", base, exact=False, drift=rec["drift"])
    ok = rec["ok"] and same["ok"] and eng["ok"]
    out = {"ok": ok, "녹화": rec, "같은녹화_편집": same, "프로그램_전체": eng}
    (work / "repro.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("1편 재현 검사:", "통과" if ok else "실패")
    return ok


def main(work: Path, only=None) -> bool:
    sc = scenario.load(EP1 / "scenario.yaml")
    work.mkdir(parents=True, exist_ok=True)
    stages = only or ("프로그램", "기준", "같은녹화", "비교")   # 프로그램과 기준을 이어서(같은 때) 찍는다
    # 녹화 둘을 연달아(같은 때) 찍고 나서 편집한다 — 컴퓨터 빠르기 차이가 섞이지 않게
    if "프로그램" in stages:            # 목소리를 먼저 만들어 기준과 함께 쓴다
        for k in ("cap.mkv.key",):         # 지난 녹화를 다시 쓰면 '같은 때' 찍은 것이 아니게 됨 → 매번 새로 녹화
            (work / "engine" / k).unlink(missing_ok=True)
        stage_engine(work, sc, ("목소리", "리허설"))
    (work / "base" / "log_rec_pre.json").unlink(missing_ok=True) if "기준" in stages else None
    if "기준" in stages and "프로그램" in stages:      # 원래 코드 → 프로그램 → 원래 코드 순서로 연달아 찍는다
        stage_base(work, sc)
        shutil.copy(work / "base" / "log_rec.json", work / "base" / "log_rec_pre.json")
    if "프로그램" in stages:
        stage_engine(work, sc, ("녹화",))
    if "기준" in stages:
        stage_base(work, sc)
    if "프로그램" in stages:
        stage_engine(work, sc, ("편집",))
    if "기준" in stages:
        build_base(work)
    if "같은녹화" in stages:
        stage_same(work, sc)
    return report(work, sc) if "비교" in stages else True

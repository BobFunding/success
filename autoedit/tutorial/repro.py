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
TOL_T = 0.25            # 녹화끼리 시각 허용 오차(초)
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
    if not (base / "cap.mkv").exists():
        _py(["record_ep1.py", "rec"], base)
        log = json.loads((base / "log_rec.json").read_text(encoding="utf-8"))
        (base / "sync.json").write_text(json.dumps({"offset": find_sync(base / "cap.mkv", log["marks"]["sync"])}))
    _py(["build_ep1.py"], base)


def stage_same(work: Path, sc) -> None:
    same = work / "same"
    same.mkdir(parents=True, exist_ok=True)
    for f in ("narration.json", "log_rec.json", "sync.json"):
        shutil.copy(work / "base" / f, same / f)
    if not (same / "cap.mkv").exists():
        (same / "cap.mkv").symlink_to((work / "base" / "cap.mkv").resolve())
    Composer(sc, same).build()


def stage_engine(work: Path, sc) -> None:
    from .rules import merged
    maker.make(sc, work / "engine", rules=merged())          # 사용자가 바꾼 규칙과 무관하게 1편 기본 규칙으로


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


def compare_logs(a: dict, b: dict) -> dict:
    """녹화 기록 비교. 시각은 본편 시작 기준으로 맞춰서 본다."""
    a0, b0 = a["marks"]["body_start"], b["marks"]["body_start"]
    res = {"clicks": [len(a["clicks"]), len(b["clicks"])], "spots": [len(a["spots"]), len(b["spots"])],
           "lines": [[x["key"] for x in a["lines"]] == [x["key"] for x in b["lines"]]]}
    dxy = [max(abs(x["x"] - y["x"]), abs(x["y"] - y["y"])) for x, y in zip(a["clicks"], b["clicks"])]
    dt = [abs((x["t"] - a0) - (y["t"] - b0)) for x, y in zip(a["clicks"], b["clicks"])]
    dbox = [max(abs(x[k] - y[k]) for k in ("x", "y", "w", "h")) for x, y in zip(a["spots"], b["spots"])]
    dst = [max(abs((x["start"] - a0) - (y["start"] - b0)), abs((x["end"] - a0) - (y["end"] - b0)))
           for x, y in zip(a["spots"], b["spots"])]
    dl = [abs((x["t"] - a0) - (y["t"] - b0)) for x, y in zip(a["lines"], b["lines"])]
    res.update(click_xy=max(dxy), click_t=max(dt), spot_box=max(dbox), spot_t=max(dst), line_t=max(dl))
    res["ok"] = (res["clicks"][0] == res["clicks"][1] and res["spots"][0] == res["spots"][1] and res["lines"][0]
                 and res["click_xy"] <= TOL_XY and res["spot_box"] <= TOL_XY
                 and max(res["click_t"], res["spot_t"], res["line_t"]) <= TOL_T)
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


def compare_outputs(a: Path, b: Path, base: str, exact: bool) -> dict:
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
        res["ok"] = (res["srt_text"] and res["srt_t"] <= TOL_T and abs(res["len"][0] - res["len"][1]) <= TOL_LEN
                     and res["format"][0] == res["format"][1] and all(q >= 99 for t, q in res["frames"][:3]))
    return res


def report(work: Path, sc) -> bool:
    base = sc.file_name
    rec = compare_logs(json.loads((work / "base" / "log_rec.json").read_text(encoding="utf-8")),
                       json.loads((work / "engine" / "log_rec.json").read_text(encoding="utf-8")))
    same = compare_outputs(work / "base", work / "same", base, exact=True)
    eng = compare_outputs(work / "base", work / "engine", base, exact=False)
    ok = rec["ok"] and same["ok"] and eng["ok"]
    out = {"ok": ok, "녹화": rec, "같은녹화_편집": same, "프로그램_전체": eng}
    (work / "repro.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("1편 재현 검사:", "통과" if ok else "실패")
    return ok


def main(work: Path, only=None) -> bool:
    sc = scenario.load(EP1 / "scenario.yaml")
    work.mkdir(parents=True, exist_ok=True)
    stages = only or ("프로그램", "기준", "같은녹화", "비교")
    if "프로그램" in stages:            # 목소리를 먼저 만들어 기준과 함께 쓴다
        stage_engine(work, sc)
    if "기준" in stages:
        stage_base(work, sc)
    if "같은녹화" in stages:
        stage_same(work, sc)
    return report(work, sc) if "비교" in stages else True

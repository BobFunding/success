"""참고 영상 스타일 따라 하기 (DESIGN.md 9.1): 영상 파일에서 '편집 기법만' 재서 스타일 카드로 만든다.

- 재는 것(AI 없이): 비율·해상도·프레임, 장면 전환 간격, 확대 횟수·배율(화면 크기 변화), 전환 방식(컷/페이드),
  자막 위치·크기·색·상자(글자 인식), 말 빠르기·문장 사이 쉼(받아쓰기), 배경음악 유무, 인트로 길이, 색감.
- 적용하는 것(우리 엔진이 할 수 있는 것만): 문장 사이 쉼, 확대·최대 확대, 말 빠르기, 자막 켜기.
  나머지는 카드에 '참고만'(색·글꼴은 브랜드가 우선) 또는 '따라 할 수 없음'으로 적는다.
- 내용은 가져오지 않는다: 카드에는 숫자만 남기고 화면·글자·소리는 저장하지 않는다. 원본 파일은 분석 뒤 지운다.
- 적용 순서(rules.merged): 1편 기본 ← 내 규칙 ← 스타일 카드 ← 브랜드 ← 장면 표. 안전 규칙은 어느 층도 끌 수 없다.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from ..ffmpeg_utils import FFMPEG, probe

STYLES = Path.home() / ".tutorial_maker" / "styles"
# 재는 방법마다 생기는 치우침을 1편에 맞춘다: 1편 최종본을 넣으면 1편 설정(쉼 0.55초, 확대 1.6배, 말 빠르기 그대로)이 나오게
# (2026-10-11 실측: 1편에서 받아쓰기 초당 3.84글자, 문장 사이 0.40초, 확대 봉우리 중앙값 1.5배)
CAL_CPS, CAL_GAP, CAL_ZOOM = 3.84, 0.55 / 0.40, 1.6 / 1.5


def _frames(video: Path, fps: float, width: int = 480):
    info = probe(video)
    w = width
    h = int(round(info.height * w / info.width / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w), info


def cuts(video: Path, thr: float = 0.3) -> list[float]:
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(video), "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", out)]


def zooms(frames: np.ndarray, fps: float, cut_t: list[float]) -> dict:
    """프레임 사이 닮음 변환(크기·이동)을 이어 붙여 '확대된 정도'를 잰다. 장면이 바뀌면 다시 1배부터."""
    import cv2
    orb = cv2.ORB_create(600)
    level, levels, moves = 1.0, [], []
    prev = None
    cut_i = {int(round(t * fps)) for t in cut_t}
    for i, f in enumerate(frames):
        kp, des = orb.detectAndCompute(f, None)
        if prev is not None and i not in cut_i and des is not None and prev[1] is not None and len(kp) > 20:
            m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(prev[1], des)
            if len(m) > 20:
                a = np.float32([prev[0][x.queryIdx].pt for x in m]); b = np.float32([kp[x.trainIdx].pt for x in m])
                M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=3)
                if M is not None and inl is not None and inl.sum() > 15:
                    s = float(np.hypot(M[0, 0], M[1, 0]))
                    if 0.8 < s < 1.25:
                        level *= s
                    moves.append(float(np.hypot(M[0, 2], M[1, 2])) / f.shape[1])
        elif i in cut_i:
            level = 1.0
        levels.append(level)
        prev = (kp, des)
    lv = np.array(levels)
    # 확대 구간: 1.12배를 넘는 연속 구간
    events, cur = [], None
    for i, v in enumerate(lv):
        if v > 1.12 and cur is None:
            cur = [i, v]
        elif v > 1.12:
            cur[1] = max(cur[1], v)
        elif cur is not None:
            events.append(cur); cur = None
    if cur is not None:
        events.append(cur)
    dur = len(frames) / fps
    peaks = [e[1] for e in events if True]
    return {"횟수": len(events), "분당": round(len(events) / max(dur / 60, 0.1), 1),
            "배율": round(float(np.median(peaks)), 2) if peaks else 1.0, "최대배율": round(float(max(peaks)), 2) if peaks else 1.0,
            "이동": round(float(np.mean(moves)) * fps, 3) if moves else 0.0}


def fades(frames: np.ndarray, fps: float, cut_t: list[float]) -> str:
    """전환 방식: 바뀌는 순간 앞뒤 0.4초 동안 밝기가 서서히 바뀌면 페이드, 한 번에 바뀌면 컷."""
    if not cut_t:
        return "없음"
    soft = 0
    for t in cut_t:
        i = int(round(t * fps))
        seg = frames[max(0, i - 2):i + 3].reshape(-1, frames.shape[1] * frames.shape[2]).astype(np.float32)
        if len(seg) >= 4:
            d = np.abs(np.diff(seg, axis=0)).mean(axis=1)
            soft += int(d.max() < 2.2 * np.median(d) + 1)
    return "페이드" if soft > len(cut_t) / 2 else "컷"


def subtitles(video: Path, info, n: int = 10, log=print) -> dict:
    """자막: 화면 아래 40% 에서 글자 인식 → 위치·크기·글자색·상자 유무. 글자 자체는 저장하지 않는다."""
    try:
        import easyocr
    except Exception:
        return {"있음": None, "이유": "글자 인식 부품이 없어 건너뜀"}
    rd = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    dur = info.duration
    ys, hs, fg, bg, hits = [], [], [], [], 0
    for k in range(n):
        t = dur * (k + 0.5) / n
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-2",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if not raw:
            continue
        H = len(raw) // (960 * 3)
        img = np.frombuffer(raw, np.uint8).reshape(H, 960, 3)
        y0 = int(H * 0.6)
        found = False
        for box, _txt, conf in rd.readtext(img[y0:]):
            if conf < 0.4:
                continue
            xs = [p[0] for p in box]; yy = [p[1] + y0 for p in box]
            bw, bh = max(xs) - min(xs), max(yy) - min(yy)
            if bw < 960 * 0.15 or abs((min(xs) + max(xs)) / 2 - 480) > 960 * 0.15:
                continue                                   # 가운데에 넓게 있는 글자줄만 자막으로 본다
            found = True
            ys.append(((min(yy) + max(yy)) / 2) / H); hs.append(bh / H)
            crop = img[int(min(yy)):int(max(yy)), int(min(xs)):int(max(xs))].reshape(-1, 3).astype(np.float32)
            lum = crop @ np.array([0.299, 0.587, 0.114])
            fg.append(crop[lum >= np.percentile(lum, 85)].mean(0)); bg.append(crop[lum <= np.percentile(lum, 40)].mean(0))
        hits += found
    if not ys:
        return {"있음": False}
    hexc = lambda c: "#%02X%02X%02X" % tuple(int(x) for x in np.median(np.array(c), axis=0))
    bgc = np.median(np.array(bg), axis=0)
    return {"있음": hits >= n * 0.3, "위치": round(float(np.median(ys)), 2), "크기": round(float(np.median(hs)), 3),
            "글자색": hexc(fg), "상자색": hexc(bg), "상자": bool(np.std(np.array(bg)[:, :3]) < 40 and bgc.mean() < 120)}


def speech(video: Path, log=print) -> dict:
    """말 빠르기(초당 글자)와 문장 사이 쉼, 배경음악(말 없는 틈의 소리 크기). 받아쓴 글은 저장하지 않는다."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    if not raw:
        return {"말": False}
    a = np.frombuffer(raw, np.float32)
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel("small", device="cpu", compute_type="int8")
        segs = list(m.transcribe(a, language="ko", vad_filter=False)[0])
    except Exception as e:
        return {"말": None, "이유": f"받아쓰기 부품이 없어 건너뜀({type(e).__name__})"}
    segs = [s for s in segs if s.text.strip()]
    if not segs:
        return {"말": False, "배경음악": bool(np.sqrt(np.mean(a ** 2)) > 0.01)}
    chars = sum(len(re.sub(r"[\s,.!?·…]", "", s.text)) for s in segs)
    talk = sum(s.end - s.start for s in segs)
    gaps = [b.start - x.end for x, b in zip(segs, segs[1:]) if 0.1 < b.start - x.end < 3]
    quiet = []
    for x, b in zip(segs, segs[1:]):
        if b.start - x.end > 0.6:
            q = a[int((x.end + 0.15) * 16000):int((b.start - 0.15) * 16000)]
            if len(q):
                quiet.append(float(np.sqrt(np.mean(q ** 2))))
    music = bool(quiet) and bool(20 * np.log10(np.median(quiet) + 1e-9) > -45)
    return {"말": True, "초당글자": round(chars / max(talk, 0.1), 2), "문장사이쉼": round(float(np.median(gaps)), 2) if gaps else None,
            "첫말": round(segs[0].start, 2), "배경음악": music}


def colors(frames: np.ndarray) -> dict:
    m = frames.mean() / 255
    return {"밝기": round(float(m), 2), "대비": round(float(frames.std() / 255), 2)}


def analyze(video: Path, name: str = "", log=print) -> dict:
    """스타일 카드(dict). 오래 걸리는 받아쓰기·글자 인식은 부품이 없으면 그 항목만 건너뛴다."""
    t0 = time.time()
    log("[스타일] 화면 움직임 재는 중")
    fr, info = _frames(video, 5)
    ct = cuts(video)
    shots = np.diff([0.0] + ct + [info.duration])
    z = zooms(fr, 5, ct)
    tr = fades(fr, 5, ct)
    log("[스타일] 자막 모양 재는 중")
    sub = subtitles(video, info, log=log)
    log("[스타일] 말 빠르기 재는 중")
    sp = speech(video, log=log)
    intro = next((t for t in ct if 3 < t < 25), None)
    card = {"이름": name or Path(video).stem, "날짜": time.strftime("%Y-%m-%d"), "원본": Path(video).name,
            "영상": {"크기": f"{info.width}×{info.height}", "비율": "세로" if info.height > info.width else "가로",
                   "fps": round(info.fps, 2), "길이": round(info.duration, 1)},
            "측정": {"장면전환": {"횟수": len(ct), "평균간격": round(float(np.median(shots)), 1) if len(shots) else None, "방식": tr},
                   "확대": z, "자막": sub, "말": sp, "인트로": intro, "색감": colors(fr)},
            "분석초": round(time.time() - t0)}
    card = json.loads(json.dumps(card, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    card["적용"], card["참고만"], card["따라할수없음"] = mapping(card)
    return card


def mapping(card: dict) -> tuple[dict, list[str], list[str]]:
    """측정값 → 우리 엔진 설정(할 수 있는 것만)."""
    m = card["측정"]
    rules, ref, cant = {}, [], []
    z = m["확대"]
    if z["횟수"] == 0:
        rules["확대"], rules["최대확대"] = 1.0, 1.0
    else:
        rules["확대"] = round(min(max(z["배율"] * CAL_ZOOM, 1.2), 2.2), 2)
        rules["최대확대"] = round(min(max(z["최대배율"] * CAL_ZOOM, rules["확대"] * 1.25), 2.6), 2)
    sp = m["말"]
    speed = 0
    if sp.get("말"):
        if sp.get("문장사이쉼"):
            rules["문장사이쉼"] = round(min(max(sp["문장사이쉼"] * CAL_GAP, 0.2), 1.5), 2)
            rules["눌러주세요뒤쉼"] = rules["문장사이쉼"]
        speed = int(round(min(max((sp["초당글자"] / CAL_CPS - 1) * 100, -10), 10) / 2) * 2)
        if sp.get("배경음악"):
            cant.append("배경음악(넣지 않아요 — 저작권이 분명한 음악만 직접 넣을 수 있게 나중 기능)")
    sub = m["자막"]
    subs = bool(sub.get("있음")) if sub.get("있음") is not None else True
    if sub.get("있음"):
        ref.append(f"자막 위치 화면 {int(sub['위치'] * 100)}% 높이 · 글자 크기 화면의 {sub['크기'] * 100:.1f}% · 글자색 {sub['글자색']}"
                   + (f" · 상자 {sub['상자색']}" if sub.get("상자") else " · 상자 없음") + " (모양·색은 브랜드를 따라요)")
    if m["장면전환"]["방식"] == "페이드":
        ref.append("전환: 페이드(우리 엔진은 인트로·아웃트로에 페이드, 본편은 이어지는 녹화)")
    if card["영상"]["비율"] == "세로":
        ref.append("세로 영상 — 결과 화면 내보내기의 세로(따라가기)를 쓰세요")
    if m["인트로"]:
        ref.append(f"인트로 약 {m['인트로']:.0f}초 (우리 인트로는 문장 길이에 맞춰 약 10초)")
    if z["이동"] > 0.08:
        cant.append("화면을 빠르게 훑는 카메라 이동")
    cant.append("3D 효과·손으로 만든 움직이는 그래픽은 따라 하지 않아요")
    return {"rules": rules, "speed": speed, "subtitles": subs}, ref, cant


# ── 저장 ──
def save(card: dict) -> Path:
    STYLES.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^\w가-힣-]+", "_", card["이름"]).strip("_") or "style"
    p = STYLES / f"{key}.json"
    p.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def cards() -> list[dict]:
    out = []
    for p in sorted(STYLES.glob("*.json")) if STYLES.exists() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["key"] = p.stem
            out.append(d)
        except Exception:
            continue
    return out


def get(key: str) -> dict | None:
    p = STYLES / f"{Path(key).name}.json"            # 경로를 넘어가지 않게 이름만
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

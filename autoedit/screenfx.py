"""화면 녹화용 편집 (Screen Studio 스타일): 배경 프레임, 자동 줌인, 부드러운 카메라, 클릭 효과, 대기 구간 빨리 감기.

기존 파이프라인(pipeline.run)과는 완전히 별개로 동작한다. 입력 영상 하나를 받아 새 영상을 만들 뿐,
다른 모듈을 고치거나 부르지 않는다. 문제가 생기면 이 파일을 쓰지 않으면 끝이다.

  python -m autoedit.screenfx 녹화.mp4 out.mp4 [--clicks clicks.json]

클릭 기록이 없으면 프레임 사이에 화면이 바뀐 곳(버튼 반응, 입력, 팝업)을 찾아 줌 대상으로 쓴다.
클릭 기록([{"t": 초, "x": px, "y": px}])이 있으면 그 좌표를 우선 쓰고 클릭 파동도 그린다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .ffmpeg_utils import FFMPEG, probe


@dataclass
class ScreenFxSettings:
    # ── 배경 프레임 ──
    background: tuple[str, str] = ("#6D5DF5", "#22C1EE")  # 대각선 그라데이션 두 색
    padding: float = 0.06            # 화면 가장자리 여백 (출력 너비 대비)
    corner_radius: float = 0.012     # 둥근 모서리 (출력 너비 대비)
    shadow: float = 0.35             # 그림자 진하기 (0~1)
    # ── 자동 줌 ──
    zoom: float = 1.8                # 기본 확대 배율
    max_zoom: float = 2.4
    hold: float = 1.6                # 마지막 활동 뒤 줌을 유지하는 시간(초)
    lead: float = 0.6                # 클릭·활동보다 얼마나 먼저 줌을 시작할지(초)
    min_activity: float = 0.6        # (클릭 기록 없을 때) 같은 자리에서 이만큼 이상 변화가 이어져야 줌함(초)
    min_hits: int = 6                # (클릭 기록 없을 때) 그 사이 실제로 바뀐 프레임이 이만큼은 있어야 줌함
    big_change: float = 0.30         # 화면의 이 비율 이상이 바뀌면(팝업·페이지 전환) 줌을 풀어서 전체를 보여줌
    stiffness: float = 0.06          # 카메라 스프링 세기 (클수록 빨리 따라감)
    damping: float = 0.55            # 카메라 스프링 감쇠 (클수록 출렁임이 적음)
    ease_in: float = 0.12            # 출발을 얼마나 부드럽게 할지 (작을수록 천천히 출발)
    # ── 빨리 감기 ──
    speedup: float = 4.0             # 대기 구간 배속 (1 이면 끔)
    idle_min: float = 1.2            # 이보다 긴 무변화 구간만 빨리 감음(초)
    idle_margin: float = 0.3         # 대기 구간 앞뒤로 원래 속도로 남길 여유(초)
    # ── 클릭 효과 ──
    click_ripple: bool = True
    # ── 출력 ──
    out_size: tuple[int, int] | None = None  # None 이면 입력과 같은 크기
    crf: int = 18
    x264_preset: str = "veryfast"


# ───────────────────────── 1) 화면 변화 분석 ─────────────────────────

@dataclass
class FrameActivity:
    t: float
    changed: float                   # 바뀐 픽셀 비율 (커서 같은 작은 점은 제외)
    any_change: bool                 # 커서 이동까지 포함해 조금이라도 바뀌었는지
    box: tuple[float, float, float, float] | None  # 바뀐 영역 (0~1 정규화 x1, y1, x2, y2)


def analyze(video: Path, fps: float, log=print, scale_w: int = 640) -> list[FrameActivity]:
    """프레임마다 이전 프레임과 비교해 바뀐 영역(커서 제외)을 구한다. 작은 해상도로 줄여서 빠르게.

    커서 구분: 커서가 있는 자리는 '들어온 프레임'과 '나간 프레임'의 차이에 연달아 나타난다.
    그래서 이번 차이와 다음 차이가 겹치는 작은 영역을 커서로 보고 지운다. 크기나 속도로 구분하면
    글자 입력(글자가 커서보다 작음)이나 느린 커서 이동을 잘못 가른다.
    """
    import cv2

    cap = cv2.VideoCapture(str(video))
    prev = None
    buf: list[tuple[float, np.ndarray | None, bool]] = []   # (시각, 차이 마스크, 변화 여부) — 몇 프레임 앞까지만 보관
    out: list[FrameActivity] = []
    last_cursor = None
    kernel = np.ones((7, 7), np.uint8)

    def tiny_parts(mask: np.ndarray) -> np.ndarray:
        """마스크에서 커서 크기 이하의 작은 덩어리만 남긴다 (차트처럼 큰 애니메이션은 커서가 아님)."""
        n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        h, w = mask.shape
        ok = [k for k in range(1, n) if st[k, 2] < w * 0.03 and st[k, 3] < h * 0.05]
        return np.isin(lab, ok) if ok else np.zeros_like(mask)

    def finalize():
        nonlocal last_cursor
        t, diff, any_change = buf.pop(0)
        if diff is None or not any_change:
            out.append(FrameActivity(t, 0.0, False, None))
            return
        nxt = next((d for _, d, a in buf if a), None)
        cursor = tiny_parts(diff & nxt) if nxt is not None else np.zeros_like(diff)
        cursor = cv2.dilate(cursor.astype(np.uint8), kernel) > 0
        content = diff & ~cursor
        if last_cursor is not None:
            content &= ~last_cursor            # 커서가 떠난 자리
        if cursor.any():
            last_cursor = cursor
        n, _, st, _ = cv2.connectedComponentsWithStats(content.astype(np.uint8), connectivity=8)
        sh, sw = diff.shape
        keep = [r for r in st[1:] if r[cv2.CC_STAT_AREA] >= 3]
        if keep:
            x1 = min(r[0] for r in keep); y1 = min(r[1] for r in keep)
            x2 = max(r[0] + r[2] for r in keep); y2 = max(r[1] + r[3] for r in keep)
            changed = sum(int(r[cv2.CC_STAT_AREA]) for r in keep) / (sw * sh)
            out.append(FrameActivity(t, changed, True, (x1 / sw, y1 / sh, x2 / sw, y2 / sh)))
        else:
            out.append(FrameActivity(t, 0.0, True, None))

    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (scale_w, round(scale_w * h / w)))
        if prev is None:
            buf.append((i / fps, None, False))
        else:
            # 압축 때문에 정지 화면도 픽셀이 미세하게 흔들린다 → 차이가 뚜렷한 픽셀만, 몇 개 이상일 때만 변화로 본다
            diff = cv2.absdiff(small, prev) > 24
            buf.append((i / fps, diff, int(diff.sum()) >= 4))
        if len(buf) > 4:
            finalize()
        prev = small
        i += 1
    while buf:
        finalize()
    cap.release()
    log(f"[화면] 프레임 {len(out)}개 분석")
    return out


# ───────────────────────── 2) 줌 계획 ─────────────────────────

@dataclass
class Focus:
    start: float
    end: float
    cx: float                        # 줌 중심 (0~1)
    cy: float
    zoom: float
    source: str                      # "click" / "auto"


def plan_focus(acts: list[FrameActivity], clicks: list[dict], W: int, H: int,
               s: ScreenFxSettings) -> list[Focus]:
    """줌 구간 목록. 클릭이 있으면 클릭 기준, 없으면 화면 변화 기준."""
    focus: list[Focus] = []
    if clicks:
        for c in clicks:
            t = float(c["t"])
            # 클릭 뒤 같은 영역에서 변화(입력 등)가 이어지면 그만큼 줌을 더 유지한다
            end = t + s.hold
            px, py = c["x"] / W, c["y"] / H
            for a in acts:
                if t < a.t <= end + 0.5 and a.box and _near(a.box, px, py, 0.18):
                    end = max(end, a.t + s.hold * 0.6)
            # 클릭 직후 1초 안에 바뀐 곳(슬라이드, 팝업, 결과 화면)까지 함께 담는다.
            # 누른 버튼보다 '누른 결과'가 보여야 하므로. 너무 넓게 바뀌면(페이지 전환) 클릭 위치만 본다
            u = [px, py, px, py]
            for a in acts:
                if t <= a.t <= t + 1.0 and a.box and a.changed < s.big_change:
                    u = [min(u[0], a.box[0]), min(u[1], a.box[1]), max(u[2], a.box[2]), max(u[3], a.box[3])]
            span = max(u[2] - u[0], (u[3] - u[1]) * H / W)
            if span > 0.08:
                z = min(s.zoom, 0.85 / span)
                if z >= 1.2:
                    px, py = (u[0] + u[2]) / 2, (u[1] + u[3]) / 2
                    focus.append(Focus(t - s.lead, end, px, py, z, "click"))
                    continue
                # 결과가 화면 대부분에 걸치면 줌하지 않고 전체를 보여준다
                focus.append(Focus(t - s.lead, end, 0.5, 0.5, 1.0, "click"))
                continue
            focus.append(Focus(t - s.lead, end, px, py, s.zoom, "click"))
    else:
        fps = 1 / (acts[1].t - acts[0].t) if len(acts) > 1 else 30.0
        hits: dict[int, int] = {}  # 줌 구간마다 실제로 변화가 있었던 프레임 수
        union: dict[int, list[float]] = {}  # 줌 구간 동안 바뀐 영역 전체
        big: dict[int, list[float]] = {}    # 그중 큰 변화(차트 등장 등 화면 내용 변화)만

        def grow(d, k, b):
            u = d.get(k)
            d[k] = list(b) if u is None else [min(u[0], b[0]), min(u[1], b[1]), max(u[2], b[2]), max(u[3], b[3])]

        def is_big(b):
            return b[2] - b[0] >= 0.08 or b[3] - b[1] >= 0.12
        cur: Focus | None = None
        for a in acts:
            if a.box is None or a.changed >= s.big_change:
                if cur and a.changed >= s.big_change:   # 팝업·페이지 전환 → 줌 풀기
                    cur.end = a.t
                    focus.append(cur)
                    cur = None
                continue
            bx, by = (a.box[0] + a.box[2]) / 2, (a.box[1] + a.box[3]) / 2
            bw, bh = a.box[2] - a.box[0], a.box[3] - a.box[1]
            # 바뀐 영역이 화면에 넉넉히 들어오는 배율 (너무 크게 잡히면 줌하지 않음)
            z = min(s.max_zoom, s.zoom, 0.55 / max(bw, bh * H / W, 1e-3))
            if z < 1.25:
                continue
            if cur and a.t - cur.end <= s.hold and _near((cur.cx, cur.cy, cur.cx, cur.cy), bx, by, 0.2):
                cur.end = a.t + s.hold
                hits[id(cur)] += 1
                grow(union, id(cur), a.box)
                if is_big(a.box):
                    grow(big, id(cur), a.box)
                continue
            if cur:
                focus.append(cur)
            cur = Focus(a.t - s.lead, a.t + s.hold, bx, by, z, "auto")
            hits[id(cur)] = 1
            grow(union, id(cur), a.box)
            if is_big(a.box):
                grow(big, id(cur), a.box)
        if cur:
            focus.append(cur)
        # 같은 자리에서 활동이 이어진 것만 줌한다 (커서가 지나간 자국, 잠깐 스친 변화는 제외)
        # 잠깐 스친 변화(깜빡임, 한 번 바뀐 버튼 색)는 줌하지 않는다
        focus = [f for f in focus if f.end - f.start >= s.lead + s.hold + s.min_activity
                 and hits[id(f)] >= s.min_hits]
        # 중심과 배율은 구간 전체에서 바뀐 영역을 다 담도록 다시 정한다 (넓게 바뀌면 덜 확대)
        # 큰 변화가 있었으면 그 영역만 본다 (커서가 다가오며 남긴 작은 자국은 무시)
        for f in focus:
            u = big.get(id(f)) or union[id(f)]
            f.cx, f.cy = (u[0] + u[2]) / 2, (u[1] + u[3]) / 2
            f.zoom = min(s.max_zoom, s.zoom, 0.8 / max(u[2] - u[0], (u[3] - u[1]) * H / W, 1e-3))
        focus = [f for f in focus if f.zoom >= 1.15]
    # 겹치면 앞 구간을 다음 구간 시작에서 끊는다 (카메라는 한 번에 한 곳만)
    focus.sort(key=lambda f: f.start)
    for a, b in zip(focus, focus[1:]):
        a.end = min(a.end, b.start)
    return [f for f in focus if f.end > f.start]


def _near(box, x, y, r) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return abs(cx - x) <= r and abs(cy - y) <= r


def camera_path(n_frames: int, fps: float, focus: list[Focus], s: ScreenFxSettings) -> np.ndarray:
    """프레임마다 (cx, cy, zoom). 목표값을 스프링으로 따라가서 Screen Studio 처럼 부드럽게 움직인다."""
    path = np.zeros((n_frames, 3))
    pos = np.array([0.5, 0.5, 1.0])
    vel = np.zeros(3)
    goal = pos.copy()                 # 목표를 한 번 거른 값 → 출발이 천천히 시작됨 (ease-in)
    k, c = s.stiffness * 30 / fps, s.damping
    ease = min(1.0, s.ease_in * 30 / fps)
    for i in range(n_frames):
        t = i / fps
        tgt = np.array([0.5, 0.5, 1.0])
        for f in focus:
            if f.start <= t < f.end:
                # 목표도 화면 안쪽으로 당겨 둔다 (가장자리 버튼을 향해 속도만 계속 쌓이지 않게)
                th = 0.5 / f.zoom
                tgt = np.array([min(max(f.cx, th), 1 - th), min(max(f.cy, th), 1 - th), f.zoom])
                break
        goal = goal + (tgt - goal) * ease
        vel = vel * (1 - c) + (goal - pos) * k
        pos = pos + vel
        if pos[2] < 1.0:
            pos[2], vel[2] = 1.0, 0.0
        # 확대된 화면이 원본 밖으로 나가지 않게 중심을 가둔다. 막힌 방향의 속도는 버린다 (안 그러면 풀릴 때 튐)
        half = 0.5 / pos[2]
        for d in (0, 1):
            clamped = min(max(pos[d], half), 1 - half)
            if clamped != pos[d]:
                pos[d], vel[d] = clamped, 0.0
        path[i] = pos
    return path


# ───────────────────────── 3) 빨리 감기 ─────────────────────────

def speed_map(acts: list[FrameActivity], focus: list[Focus], s: ScreenFxSettings) -> list[int]:
    """출력에 쓸 원본 프레임 번호 목록. 화면이 전혀 안 바뀌는 대기 구간은 배속(프레임 건너뛰기)."""
    n = len(acts)
    if s.speedup <= 1 or n == 0:
        return list(range(n))
    fps = 1 / (acts[1].t - acts[0].t) if n > 1 else 30.0
    idle = np.array([not a.any_change for a in acts])
    fast = np.zeros(n, bool)
    i = 0
    while i < n:
        if idle[i]:
            j = i
            while j < n and idle[j]:
                j += 1
            if (j - i) / fps >= s.idle_min:
                m = int(s.idle_margin * fps)
                fast[i + m: j - m] = True
            i = j
        else:
            i += 1
    # 줌이 막 시작되거나 끝나는 순간은 빨리 감지 않는다 (카메라 움직임이 튀지 않게)
    for f in focus:
        for edge in (f.start, f.end):
            a, b = int((edge - 0.4) * fps), int((edge + 0.4) * fps)
            fast[max(0, a):max(0, b)] = False
    frames, acc = [], 0.0
    for i in range(n):
        if fast[i]:
            acc += 1 / s.speedup
            if acc >= 1 - 1e-9:
                acc -= 1
                frames.append(i)
        else:
            acc = 0.0
            frames.append(i)
    return frames


# ───────────────────────── 4) 합성 ─────────────────────────

def _hex(c: str) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16)], np.float32)  # BGR


def _background(W: int, H: int, s: ScreenFxSettings) -> np.ndarray:
    a, b = _hex(s.background[0]), _hex(s.background[1])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    p = ((xx / W) * 0.6 + (yy / H) * 0.4)[..., None]
    return (a * (1 - p) + b * p).astype(np.uint8)


def _round_mask(w: int, h: int, r: int) -> np.ndarray:
    import cv2
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
        cv2.circle(m, (cx, cy), r, 255, -1, lineType=cv2.LINE_AA)
    return m.astype(np.float32)[..., None] / 255.0


def render(video: Path, out: Path, s: ScreenFxSettings | None = None, clicks: list[dict] | None = None,
           log=print, blurs: list[dict] | None = None, spots: list[dict] | None = None,
           out_fps: float | None = None) -> dict:
    """영상을 편집해 out 에 쓴다. 돌려주는 값: 편집 계획(줌 구간, 배속 결과) — 나레이션 정렬 등에 쓰임.

    blurs: 개인정보 흐림 [{start, end, x, y, w, h}] (원본 픽셀) — 확대돼도 같이 따라가도록 원본에 먼저 적용
    spots: 디밍 [{start, end, x, y, w, h}] — 이 영역만 밝게 두고 나머지를 어둡게 (누를 곳 강조)
    out_fps: 출력 프레임 수 (예: 원본 30 → 60). 카메라 움직임은 출력 프레임마다 계산해서 더 부드러워짐
    """
    import cv2

    s = s or ScreenFxSettings()
    clicks = clicks or []
    blurs = blurs or []
    spots = spots or []
    info = probe(video)
    fps, SW, SH = info.fps, info.width, info.height
    W, H = s.out_size or (SW, SH)

    acts = analyze(video, fps, log)
    focus = plan_focus(acts, clicks, SW, SH, s)
    path = camera_path(len(acts), fps, focus, s)
    frames = speed_map(acts, focus, s)
    log(f"[화면] 줌 {len(focus)}곳, {len(acts) / fps:.1f}초 → {len(frames) / fps:.1f}초")

    # 창 크기와 위치 (배경 여백 안쪽, 원본 비율 유지)
    pad = int(W * s.padding)
    cw = W - 2 * pad
    ch = round(cw * SH / SW)
    if ch > H - 2 * pad:
        ch = H - 2 * pad
        cw = round(ch * SW / SH)
    ox, oy = (W - cw) // 2, (H - ch) // 2
    r = max(4, int(W * s.corner_radius))
    mask = _round_mask(cw, ch, r)
    bg = _background(W, H, s).astype(np.float32)
    # 그림자: 창 모양을 아래로 살짝 내리고 크게 흐림
    sh = np.zeros((H, W), np.float32)
    sh[oy + int(H * 0.012): oy + int(H * 0.012) + ch, ox: ox + cw] = mask[..., 0]
    sh = cv2.GaussianBlur(sh, (0, 0), W * 0.012)[..., None] * s.shadow
    base = bg * (1 - sh)

    sub = max(1, round((out_fps or fps) / fps))   # 원본 한 프레임당 출력 프레임 수
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", f"{fps * sub:.5f}", "-i", "-", "-c:v", "libx264", "-preset", s.x264_preset,
           "-crf", str(s.crf), "-pix_fmt", "yuv420p", "-g", str(int(round(fps * sub * 2))),
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-movflags", "+faststart", str(out)]
    spot_masks: dict[int, np.ndarray] = {}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cap = cv2.VideoCapture(str(video))
    want = iter(frames)
    nxt = next(want, None)
    idx = 0
    click_ts = [(float(c["t"]), c["x"] / SW, c["y"] / SH) for c in clicks] if s.click_ripple else []
    try:
        while nxt is not None:
            ok, frame = cap.read()
            if not ok:
                break
            if idx != nxt:
                idx += 1
                continue
            frame = _apply_privacy_and_spots(frame, idx / fps, blurs, spots, spot_masks)
            for j in range(sub):
                # 출력 프레임 사이 카메라 위치는 앞뒤 원본 프레임 사이를 보간 (60fps 출력에서 더 부드럽게)
                f2 = j / sub
                nx = min(idx + 1, len(path) - 1)
                cx, cy, z = path[idx] * (1 - f2) + path[nx] * f2
                t = (idx + f2) / fps
                proc.stdin.write(_compose(frame, cx, cy, z, t, SW, SH, cw, ch, ox, oy, base, mask, click_ts)
                                 .tobytes())
            idx += 1
            nxt = next(want, None)
    finally:
        cap.release()
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg 인코딩 실패")
    plan = {"settings": asdict(s), "focus": [asdict(f) for f in focus],
            "frames_in": len(acts), "frames_out": len(frames) * sub, "fps": fps * sub,
            # 출력 시각 → 원본 시각 (나레이션·자막을 원본 기준으로 맞출 때 사용)
            "out_to_src": [round(i / fps, 3) for i in frames[:: max(1, int(fps // 10))]]}
    return plan


def _apply_privacy_and_spots(frame, t, blurs, spots, cache):
    """원본 프레임에 개인정보 흐림과 디밍을 먼저 적용한다 (그래야 확대·이동해도 정확히 따라감)."""
    import cv2
    for b in blurs:
        if b["start"] <= t <= b["end"]:
            x, y, w, h = int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"])
            roi = frame[y:y + h, x:x + w]
            if roi.size:
                # 강하게 흐린 뒤 살짝 밝혀서 '가려진 칸'처럼 자연스럽게 (모자이크보다 덜 거슬림)
                k = max(3, (h // 2) | 1)
                frame[y:y + h, x:x + w] = cv2.addWeighted(cv2.GaussianBlur(roi, (k * 2 + 1, k * 2 + 1), 0), 0.85,
                                                          np.full_like(roi, 245), 0.15, 0)
    alpha = 0.0
    m = None
    for i, sp in enumerate(spots):
        fade = 0.3
        a = min(1.0, (t - sp["start"]) / fade, (sp["end"] - t) / fade)
        if a > 0:
            if i not in cache:
                cache[i] = _spot_mask(frame.shape[1], frame.shape[0], sp)
            alpha, m = a, cache[i]
            break
    if m is not None:
        dim = 1 - 0.30 * alpha * (1 - m)          # 영역 밖을 최대 30% 어둡게 (너무 어두우면 흰 화면이 탁해 보임), 경계는 부드럽게
        frame = (frame.astype(np.float32) * dim[..., None]).astype(np.uint8)
    return frame


def _spot_mask(w, h, sp):
    import cv2
    pad = 14
    m = np.zeros((h, w), np.float32)
    x1, y1 = max(0, int(sp["x"]) - pad), max(0, int(sp["y"]) - pad)
    x2, y2 = min(w, int(sp["x"] + sp["w"]) + pad), min(h, int(sp["y"] + sp["h"]) + pad)
    cv2.rectangle(m, (x1, y1), (x2, y2), 1.0, -1)
    return cv2.GaussianBlur(m, (0, 0), 10)


def _compose(frame, cx, cy, z, t, SW, SH, cw, ch, ox, oy, base, mask, click_ts):
    """확대·클릭 파동·배경 합성 → 출력 한 프레임."""
    import cv2
    # 확대: 원본에서 (cx, cy) 중심으로 1/z 크기 영역을 잘라 창 크기로 키움
    vw, vh = SW / z, SH / z
    x0, y0 = cx * SW - vw / 2, cy * SH - vh / 2
    M = np.array([[cw / vw, 0, -x0 * cw / vw], [0, ch / vh, -y0 * ch / vh]], np.float32)
    view = cv2.warpAffine(frame, M, (cw, ch), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    for ct, px, py in click_ts:
        age = t - ct
        if 0 <= age < 0.55:
            # 클릭 파동: 커지면서 옅어지는 원 두 겹
            sx, sy = (px * SW - x0) * cw / vw, (py * SH - y0) * ch / vh
            p = age / 0.55
            rad = int((10 + 40 * p) * z * cw / SW)
            ov = view.copy()
            cv2.circle(ov, (int(sx), int(sy)), rad, (255, 255, 255), max(2, int(4 * cw / SW * z)), cv2.LINE_AA)
            cv2.circle(ov, (int(sx), int(sy)), max(2, rad // 3), (36, 20, 204), -1, cv2.LINE_AA)  # 로고 빨강 #CC1424
            view = cv2.addWeighted(ov, 0.75 * (1 - p), view, 1 - 0.75 * (1 - p), 0)
    canvas = base.copy()
    region = canvas[oy:oy + ch, ox:ox + cw]
    canvas[oy:oy + ch, ox:ox + cw] = region * (1 - mask) + view.astype(np.float32) * mask
    return canvas.astype(np.uint8)


def main() -> None:
    p = argparse.ArgumentParser(description="화면 녹화 편집 (배경 프레임·자동 줌·빨리 감기)")
    p.add_argument("video")
    p.add_argument("out")
    p.add_argument("--clicks", help="클릭 기록 JSON [{t, x, y}] (없으면 화면 변화로 자동 추정)")
    p.add_argument("--no-speedup", action="store_true")
    p.add_argument("--zoom", type=float, default=ScreenFxSettings.zoom)
    p.add_argument("--bg", default=",".join(ScreenFxSettings.background), help="배경 그라데이션 두 색 (#RRGGBB,#RRGGBB)")
    a = p.parse_args()
    s = ScreenFxSettings(zoom=a.zoom, background=tuple(a.bg.split(",")[:2]),
                         speedup=1.0 if a.no_speedup else ScreenFxSettings.speedup)
    clicks = json.loads(Path(a.clicks).read_text(encoding="utf-8")) if a.clicks else None
    plan = render(Path(a.video), Path(a.out), s, clicks)
    Path(a.out).with_suffix(".plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

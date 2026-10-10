"""화면 캡처 (DESIGN.md 5.3, 1단계 검증 결과 tutorials/capture_check/RESULT.md).

CDP 화면 전송은 초당 7~14장·1초 멈춤이라 쓰지 않는다. 두 가지 방식을 쓰고, 사용자는 고르지 않는다(capture_method).
- x11: Linux. Xvfb 가상 화면 + ffmpeg x11grab 무손실(1편 방식). 가상 화면이라 모니터 크기와 무관.
- frames(한 장씩 찍기): Windows·Mac, 또는 Xvfb 가 없을 때. 창 없는 브라우저를 k배 느리게 조작하면서 화면 사진을
  계속 찍고, 찍은 시각을 k로 나눠 원래 빠르기 영상으로 만든다. 모니터와 무관하고 화질은 화면 사진 그대로(2880x1620).
  화면 애니메이션(CSS)도 k배 느리게 걸어 둔다. 1분 영상에 k분 안팎.
  (모니터가 2880x1620 이상인 Windows·Mac 에서 운영체제 캡처를 쓰는 길은 아직 없음 — 한 장씩 찍기만으로 동작한다)
"""
from __future__ import annotations

import math
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from ..ffmpeg_utils import FFMPEG, FFPROBE


class CaptureUnavailable(RuntimeError):
    pass


class X11Capture:
    """Xvfb 가상 화면을 띄우고 그 화면을 무손실로 찍는다(1편과 같은 설정)."""

    def __init__(self, width: int, height: int, fps: int = 30, display: str = ":99"):
        if not shutil.which("Xvfb"):
            raise CaptureUnavailable("Xvfb 가 없어요. 설치: sudo apt install xvfb")
        self.w, self.h, self.fps, self.display = width, height, fps, display
        self.xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", f"{width}x{height}x24", "-nocursor"],
                                     stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        self.proc = None

    @property
    def env(self) -> dict:
        return dict(os.environ, DISPLAY=self.display)

    def start(self, out: Path) -> None:
        self.proc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "x11grab", "-framerate", str(self.fps),
                                      "-video_size", f"{self.w}x{self.h}", "-draw_mouse", "0", "-i", self.display,
                                      "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0", str(out)],
                                     stdin=subprocess.PIPE)

    def stop(self) -> None:
        if self.proc:
            self.proc.communicate(b"q", timeout=60)
            self.proc = None

    def close(self) -> None:
        self.stop()
        self.xvfb.terminate()


def capture_method() -> str:
    """TUTORIAL_CAPTURE=x11|frames 로 강제할 수 있다(검사용). 기본: Linux + Xvfb 면 x11, 아니면 frames."""
    m = os.environ.get("TUTORIAL_CAPTURE", "")
    if m in ("x11", "frames"):
        return m
    return "x11" if platform.system() == "Linux" and shutil.which("Xvfb") else "frames"


class FrameCapture:
    """한 장씩 찍기. 녹화기의 기다리는 시간(hold) 동안 쉬지 않고 사진을 찍는다."""

    FPS = 30

    def __init__(self, page, ctx, out_dir: Path):
        self.pg, self.ctx, self.dir = page, ctx, out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in out_dir.glob("*.jpg"):
            f.unlink()
        self.times: list[float] = []
        self.t0, self.k = time.monotonic(), 1.0
        self.cdp = None
        self.shot_sec = 0.15

    def shoot(self) -> None:
        t = (time.monotonic() - self.t0) / self.k
        data = self.pg.screenshot(type="jpeg", quality=92, caret="initial", timeout=10000)
        (self.dir / f"{len(self.times):06d}.jpg").write_bytes(data)
        self.times.append(t)

    def hold(self, real_sec: float) -> None:
        """real_sec 동안 찍는다. 남은 시간이 한 장 찍는 시간보다 짧으면 그냥 기다린다(박자 유지)."""
        end = time.monotonic() + real_sec
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return
            if left < self.shot_sec * 0.8:
                time.sleep(left)
                return
            a = time.monotonic()
            self.shoot()
            self.shot_sec = 0.7 * self.shot_sec + 0.3 * (time.monotonic() - a)

    def choose_speed(self, url: str) -> float:
        """사진 한 장 찍는 시간을 재서, 초당 30장이 되게 느리게 돌릴 배수를 정한다(3~12배)."""
        self.pg.goto(url, wait_until="networkidle", timeout=60000)
        ts = []
        for _ in range(5):
            a = time.monotonic()
            self.pg.screenshot(type="jpeg", quality=92, caret="initial")
            ts.append(time.monotonic() - a)
        self.shot_sec = sorted(ts)[2]
        k = float(min(12, max(3, math.ceil(self.shot_sec * self.FPS * 1.15))))
        self.slow_animations(k)
        return k

    def slow_animations(self, k: float | None = None) -> None:
        """화면 애니메이션(CSS·Web Animations)을 k배 느리게."""
        k = k or self.k
        try:
            if self.cdp is None:
                self.cdp = self.ctx.new_cdp_session(self.pg)
                self.cdp.send("Animation.enable")
            self.cdp.send("Animation.setPlaybackRate", {"playbackRate": 1.0 / k})
        except Exception:
            self.cdp = None

    def encode(self, out: Path) -> None:
        """찍은 사진을 찍은 시각대로 놓아 일정 프레임(30fps) 무손실 영상으로."""
        if not self.times:
            raise RuntimeError("찍힌 화면이 없어요.")
        lst = self.dir / "list.txt"
        with lst.open("w", encoding="utf-8") as f:
            for i, t in enumerate(self.times):
                d = (self.times[i + 1] - t) if i + 1 < len(self.times) else 0.5
                f.write(f"file '{(self.dir / f'{i:06d}.jpg').resolve().as_posix()}'\nduration {max(d, 0.001):.4f}\n")
            f.write(f"file '{(self.dir / f'{len(self.times) - 1:06d}.jpg').resolve().as_posix()}'\n")
        first = self.times[0]
        # 첫 사진이 0초보다 늦게 찍혔으면 그만큼 앞을 첫 사진으로 채운다(기록 시각과 영상 시각을 같게)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", f"tpad=start_duration={first:.4f}:start_mode=clone,fps={self.FPS}",
                        "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0", str(out)], check=True)


def open_capture(width: int, height: int, fps: int = 30):
    system = platform.system()
    if system == "Linux":
        return X11Capture(width, height, fps)
    raise CaptureUnavailable(f"{system} 화면 캡처는 아직 준비 중이에요(16절 10단계). 지금은 Linux 에서만 녹화할 수 있어요.")


def find_sync(video: Path, mark_t: float, search: float = 30.0) -> float:
    """녹화 시작 직후 0.3초 검은 화면을 찾아 '영상 시각 = 기록 시각 + offset' 의 offset 을 돌려준다."""
    W, H = 64, 36
    raw = subprocess.run([FFMPEG, "-v", "error", "-t", f"{search}", "-i", str(video), "-vf", f"scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
    fps = _fps(video)
    is_dark = (fr.reshape(len(fr), -1) < 16).mean(1) > 0.97     # 커서는 검은 화면 위에도 그려짐
    lit = np.where(~is_dark)[0]
    # 창이 뜨기 전의 검은 화면은 건너뛰고, 밝은 화면 뒤에 처음 나오는 검은 화면
    dark = np.where(is_dark & (np.arange(len(fr)) > (lit[0] if len(lit) else 0)))[0]
    if not len(dark):
        raise RuntimeError("녹화에서 동기 표시(검은 화면)를 찾지 못했어요.")
    return round(dark[0] / fps - mark_t, 4)


def _fps(video: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v", "-show_entries", "stream=r_frame_rate",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    a, b = out.split("/")
    return float(a) / float(b)

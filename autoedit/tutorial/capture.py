"""화면 캡처 (DESIGN.md 5.3, 1단계 검증 결과 tutorials/capture_check/RESULT.md).

CDP 화면 전송은 초당 7~14장·1초 멈춤이라 쓰지 않는다. 운영체제 화면 캡처(1편 방식)가 기본이다.
- Linux: Xvfb 가상 화면 + ffmpeg x11grab 무손실. 가상 화면이라 모니터 크기와 무관하다. (검증 완료)
- Windows·Mac: 모니터가 녹화 크기보다 작으면 "한 장씩 찍기"로 자동 전환하기로 함(사용자 확인 2026-10-10). 아직 미구현.
"""
from __future__ import annotations

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

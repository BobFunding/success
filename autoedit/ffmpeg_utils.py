from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    # winget 설치 직후에는 PATH 가 갱신되지 않은 셸이 많아서 직접 찾아본다
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [local / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"]
    candidates += sorted((local / "Microsoft" / "WinGet" / "Packages").glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"))
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError(f"{name} 를 찾을 수 없습니다. `winget install Gyan.FFmpeg` 로 설치해주세요.")


FFMPEG = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


def probe(path: str | Path) -> VideoInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    if not 1 <= fps <= 240:
        fps = 30.0
    width, height = int(v["width"]), int(v["height"])
    rotation = _rotation(v)
    if rotation in (90, 270):
        width, height = height, width
    return VideoInfo(width, height, fps, float(data["format"]["duration"]), has_audio)


def _rotation(stream: dict) -> int:
    tags = stream.get("tags", {})
    if "rotate" in tags:
        return abs(int(tags["rotate"])) % 360
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:
            return abs(int(sd["rotation"])) % 360
    return 0


@lru_cache
def ffmpeg_major_version() -> int:
    out = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True).stdout
    m = re.search(r"ffmpeg version n?(\d+)", out)
    return int(m.group(1)) if m else 6


def filter_script_args(script_path: Path) -> list[str]:
    """긴 필터 그래프는 파일로 넘긴다 (ffmpeg 7 부터 문법이 바뀜)."""
    if ffmpeg_major_version() >= 7:
        return ["-/filter_complex", str(script_path)]
    return ["-filter_complex_script", str(script_path)]


@lru_cache
def has_nvenc() -> bool:
    try:
        r = subprocess.run(
            [FFMPEG, "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        return r.returncode == 0
    except Exception:
        return False


def video_encoder_args(cq: int) -> list[str]:
    if has_nvenc():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(cq), "-pix_fmt", "yuv420p"]


def run_ffmpeg(args: list[str], log=print) -> None:
    cmd = [FFMPEG, "-hide_banner", "-y", "-loglevel", "error", "-stats"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode}):\n{tail}")


def extract_audio(video: Path, wav: Path, sample_rate: int = 16000) -> None:
    run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(wav)])

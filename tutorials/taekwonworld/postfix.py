"""보내기 전 손질: 빈 화면(로딩 원·흰/회색 막·빈 줌)을 찾고, 덮거나 잘라 낸다.
사용:
  python postfix.py scan <영상.mp4>                         # 0.3초 넘는 빈 화면 후보 출력(0.1초 단위)
  python postfix.py fix <영상.mp4> <자막.srt> <출력.mp4> <규칙.json>
규칙.json: {"freeze": [[시작, 끝, 채울그림시각], ...], "cut": [[시작, 끝], ...]}   (모두 원본 영상 시각, 초)
- freeze: 그 구간을 '채울그림시각'의 화면으로 덮는다. 자막 띠(아래 140px)는 덮지 않아 자막이 목소리와 어긋나지 않는다.
- cut: 영상·소리를 함께 잘라 낸다(목소리 없는 로딩 구간만). 자막 SRT 시각도 그만큼 당긴다(출력.srt).
- 후보는 사람이(프레임을 보고) 고른다: 줌으로 빈 칸이 커 보이는 정상 화면도 후보에 걸리기 때문.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KEEP_BOTTOM = 140        # 2560x1440 기준 자막 띠 높이(이 아래는 덮지 않음)


def scan(video: str, thr: float = 9.5, min_len: float = 0.3) -> list[tuple[float, float]]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", "fps=10,scale=192:108,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 108, 192).astype(np.float32)
    std = f[:, 12:88, 20:172].reshape(len(f), -1).std(axis=1)       # 파란 배경·자막을 뺀 화면 안쪽
    runs, s = [], None
    for i, b in enumerate(std < thr):
        if b and s is None:
            s = i
        if not b and s is not None:
            runs.append((s / 10, i / 10)); s = None
    if s is not None:
        runs.append((s / 10, len(std) / 10))
    return [r for r in runs if r[1] - r[0] >= min_len]


def _tp(s):
    h, m, r = s.split(":"); sec, ms = r.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def _ts(x):
    h, m, s = int(x // 3600), int(x % 3600 // 60), x % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def fix(video: str, srt: str, out: str, rules: dict) -> None:
    freeze, cuts = rules.get("freeze", []), sorted(rules.get("cut", []))
    work = Path(out).with_suffix("")
    args = ["ffmpeg", "-v", "error", "-y", "-i", video]
    for i, (a, b, t) in enumerate(freeze):
        png = f"{work}_still{i}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", png], check=True)
        im = Image.open(png); im.crop((0, 0, im.width, im.height - KEEP_BOTTOM)).save(png)
        args += ["-i", png]
    fc, cur = [], "[0:v]"
    for i, (a, b, t) in enumerate(freeze):
        fc.append(f"{cur}[{i + 1}:v]overlay=0:0:enable='between(t,{a},{b})'[v{i}]"); cur = f"[v{i}]"
    keep, s = [], 0.0
    for a, b in cuts:
        keep.append((s, a)); s = b
    keep.append((s, None)); n = len(keep)
    fc.append(f"{cur}split={n}" + "".join(f"[x{i}]" for i in range(n)))
    fc.append(f"[0:a]asplit={n}" + "".join(f"[y{i}]" for i in range(n)))
    for i, (a, b) in enumerate(keep):
        tr = f"start={a}" + (f":end={b}" if b else "")
        fi = ("afade=t=in:d=0.04," if i else "") + (f"afade=t=out:st={b - a - 0.04}:d=0.04," if b else "")
        fc.append(f"[x{i}]trim={tr},setpts=PTS-STARTPTS[p{i}]")
        fc.append(f"[y{i}]atrim={tr},asetpts=PTS-STARTPTS,{fi}anull[q{i}]")
    fc.append("".join(f"[p{i}][q{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[ov][oa]")
    args += ["-filter_complex", ";".join(fc), "-map", "[ov]", "-map", "[oa]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    subprocess.run(args, check=True)

    def shift(x):
        d = 0.0
        for a, b in cuts:
            if x >= b:
                d += b - a
            elif x > a:
                return a - d
        return x - d
    text = Path(srt).read_text(encoding="utf-8")
    text = re.sub(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)",
                  lambda m: f"{_ts(shift(_tp(m.group(1))))} --> {_ts(shift(_tp(m.group(2))))}", text)
    Path(out).with_suffix(".srt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "scan":
        print(json.dumps(scan(sys.argv[2])))
    else:
        fix(sys.argv[2], sys.argv[3], sys.argv[4], json.loads(Path(sys.argv[5]).read_text(encoding="utf-8")))
        print("손질 끝:", sys.argv[4])

"""보내기 전 '돌발 컷' 점검: 완성 영상에서 화면이 갑자기 크게 바뀌는 곳을 찾아, 문장 경계가 아닌 곳을 표시한다.
사용: python cutcheck.py <영상.mp4> <작업폴더(timeline.json 있는 곳)> [출력.png]
- 0.1초마다 작은 회색 그림으로 줄여 앞 그림과의 차이를 잰다.
- 큰 변화가 문장 시작 ±0.4초 밖이면 '돌발', 1.5초 안에 큰 변화가 두 번 이상이면 '깜빡임'(빈 화면이 잠깐 비치는 경우)으로 본다.
- 표시된 곳마다 앞·뒤 그림을 붙여 한 장(출력.png)으로 만든다 → 눈으로 확인하고 고친 뒤에 보낸다.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

W, H, FPS = 96, 54, 10
JUMP = 18.0          # 회색 평균 차이(0~255)가 이보다 크면 '큰 변화'


def frames(video: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={FPS},scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


def check(video: str, work: str, out: str | None = None) -> list[dict]:
    tl = json.loads((Path(work) / "timeline.json").read_text(encoding="utf-8"))
    starts = [l["t"] for l in tl["lines"]] + [tl["intro"], tl["intro"] + tl["body"]]
    f = frames(video)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    jumps = [(i + 1) / FPS for i in np.where(d > JUMP)[0]]
    marks = []
    for k, t in enumerate(jumps):
        near = min(abs(t - s) for s in starts)
        burst = [u for u in jumps if 0 < u - t <= 1.5]
        if burst:
            marks.append({"t": round(t, 1), "종류": "깜빡임", "다음": round(burst[0], 1)})
        elif near > 0.4:
            marks.append({"t": round(t, 1), "종류": "돌발", "문장 경계와": round(near, 1)})
    if out and marks:
        thumbs = []
        for m in marks[:24]:
            row = []
            for dt in (-0.3, 0.0, 0.3, 0.8):
                i = max(0, min(len(f) - 1, int((m["t"] + dt) * FPS)))
                im = Image.fromarray(f[i].astype(np.uint8)).resize((W * 3, H * 3))
                ImageDraw.Draw(im).text((3, 3), f'{m["t"] + dt:.1f}', fill=255)
                row.append(im)
            thumbs.append(row)
        sheet = Image.new("L", (W * 3 * 4, H * 3 * len(thumbs)))
        for r, row in enumerate(thumbs):
            for c, im in enumerate(row):
                sheet.paste(im, (c * W * 3, r * H * 3))
        sheet.save(out)
    return marks


if __name__ == "__main__":
    res = check(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps(res, ensure_ascii=False))
    print(f"점검: 표시 {len(res)}곳" if res else "점검: 돌발 컷 없음")

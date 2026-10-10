"""캡처 결과 비교: 움직이는 구간의 실제 새 프레임 수(초당), 프레임 간격, 정지 화면 화질(기준 사진 대비 PSNR).
python analyze.py x11 cdp cdp-head cdp-jpeg"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

out = Path(__file__).parent / "out"
W, H = 2880, 1620
SW, SH = 960, 540                   # 비교용 축소 크기 (새 프레임 판정만)


def read_frames(mkv, fps=60):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mkv), "-vf", f"scale={SW}:{SH}:flags=area", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, SH, SW)


def frame_at(mkv, t):
    """t 초 프레임을 2880x1620 으로 (작게 찍힌 영상은 늘려서 → 늘린 만큼 흐려진 것이 PSNR 에 드러남)"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mkv), "-frames:v", "1",
                          "-vf", f"scale={W}:{H}:flags=lanczos", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3)


def size(mkv):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0:s=x", str(mkv)], capture_output=True, text=True).stdout.strip()


def psnr(a, b):
    m = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    return 99.0 if m == 0 else 10 * np.log10(255 ** 2 / m)


def counters(mkv):
    """프레임마다 왼쪽 위 12칸 막대를 읽어 그 화면이 그려진 시각(1/60초 단위 번호)을 얻는다."""
    w = int(size(mkv).split("x")[0])
    k = w / 1920 * 16                           # 막대 한 칸 크기(영상 픽셀)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mkv), "-vf", f"crop={int(k*12)}:{int(k)}:0:0", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, int(k), int(k * 12))
    bits = fr[:, int(k / 2), (np.arange(12) * k + k / 2).astype(int)] > 128
    return (bits * (1 << np.arange(11, -1, -1))).sum(1)


def motion_stats(cnt, t0, t1, fps=60):
    """t0~t1(영상 시각) 구간: 담긴 서로 다른 화면 수/초, 이웃 화면 사이 실제 시간 간격(중앙·최대), 재생 시각 오차."""
    seg = cnt[int(t0 * fps):int(t1 * fps)]
    idx = [0] + [i for i in range(1, len(seg)) if seg[i] != seg[i - 1]]
    real = np.diff(seg[idx]) % 4096 / 60                     # 화면이 실제로 그려진 시각 차
    play = np.diff(idx) / fps                                 # 영상에서 보이는 시각 차
    drift = np.abs(np.cumsum(real) - np.cumsum(play)).max() if len(real) else 0
    return len(idx) / (t1 - t0), np.median(real) * 1000, real.max() * 1000, drift * 1000


rows = []
for tag in sys.argv[1:]:
    info = json.loads((out / f"{tag}_frames.json").read_text())
    m = info["marks"]
    mkv = out / f"{tag}.mkv"
    cnt = counters(mkv)
    # x11 은 ffmpeg 시작 직후가 기록 기준 시각, CDP 영상은 첫 프레임이 0초
    off = -info["frame_t"][0] if "frame_t" in info else 0.0
    scroll = motion_stats(cnt, m["scroll"] + off, m["glide"] + off)
    glide = motion_stats(cnt, m["glide"] + off, m["glide_end"] + off)
    fr = cnt
    still = frame_at(mkv, min(m["still"] + 0.2 + off, len(cnt) / 60 - 0.1))
    ref = np.asarray(Image.open(out / f"{tag}_still.png").convert("RGB"))
    h = min(H, ref.shape[0]); q = psnr(still[:h, :, :], ref[:h, :W])   # 창이 작게 뜬 경우 겹치는 부분만
    rows.append((tag, size(mkv), glide, scroll, q, mkv.stat().st_size / 1e6))
    if "frame_t" in info:
        d = np.diff(info["frame_t"])
        print(f"{tag}: 받은 프레임 {len(info['frame_t'])}장, 간격 중앙 {np.median(d)*1000:.0f}ms, 최대 {d.max()*1000:.0f}ms")

print("\n| 방식 | 해상도 | 스크롤: 화면/초, 간격 중앙·최대, 시각 오차 | 커서 이동: 화면/초, 간격 중앙·최대, 시각 오차 | 정지 화면 PSNR | 크기 |")
print("|---|---|---|---|---|---|")
for tag, res, g, s, q, mb in rows:
    f = lambda v: f"{v[0]:.0f}, {v[1]:.0f}·{v[2]:.0f}ms, {v[3]:.0f}ms"
    print(f"| {tag} | {res} | {f(s)} | {f(g)} | {q:.1f} dB | {mb:.0f}MB |")

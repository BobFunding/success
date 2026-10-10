"""튜토리얼 메이커 1단계: 화면 캡처 방식 검증 (DESIGN.md 16절 1단계, 5.3절).
같은 장면(태권월드 첫 화면 → 커서 이동 → 로그인(관장) 클릭 → 로그인 화면 스크롤)을 두 방식으로 찍는다.

python capture_check.py x11   → 1편 방식: Xvfb + ffmpeg x11grab 무손실 (Linux 전용)
python capture_check.py cdp   → CDP 화면 전송(Page.startScreencast), 운영체제 무관
python capture_check.py cdp-head → CDP 화면 전송, 창 띄운 상태(Xvfb)

결과: out/<방식>.mkv, out/<방식>_frames.json(프레임 시각), out/<방식>_still.png(마지막 정지 화면 기준 사진)
"""
import base64, json, os, subprocess, sys, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

MODE = sys.argv[1] if len(sys.argv) > 1 else "cdp"
FMT = os.environ.get("CDP_FMT", "png")
TAG = MODE if MODE == "x11" or FMT == "png" else f"{MODE}-{FMT}"   # 결과 파일 이름
FPS = int(os.environ.get("FPS", "60"))
here = Path(__file__).parent
out = here / "out"
out.mkdir(exist_ok=True)
W, H, SCALE = 1920, 1080, 1.5            # 1편과 같은 CSS 크기·배율 → 2880x1620
PW, PH = int(W * SCALE), int(H * SCALE)
CHROME = "/opt/pw-browsers/chromium"
CURSOR = (here.parent / "ep1" / "record_ep1.py").read_text(encoding="utf-8").split('CURSOR = """', 1)[1].split('"""', 1)[0]
pos = [960.0, 640.0]
# 검사용: 화면 왼쪽 위에 브라우저 그리기 횟수(requestAnimationFrame)를 12칸 흑백 막대로 표시
# → 영상에서 읽으면 실제로 담긴 프레임 수·빠진 프레임을 정확히 셀 수 있다
COUNTER = """(() => { const add = () => { if (document.getElementById('__cnt')) return; const d = document.createElement('div'); d.id='__cnt';
  d.style.cssText='position:fixed;left:0;top:0;width:192px;height:16px;z-index:2147483647;pointer-events:none;display:flex';
  const c = []; for (let i = 0; i < 12; i++) { const b = document.createElement('div'); b.style.cssText='width:16px;height:16px'; d.appendChild(b); c.push(b); }
  document.documentElement.appendChild(d);
  const f = () => { const n = Math.floor((performance.timeOrigin + performance.now()) / (1000/60)) % 4096;
    for (let i = 0; i < 12; i++) c[i].style.background = (n >> (11 - i)) & 1 ? '#fff' : '#000'; requestAnimationFrame(f); };
  requestAnimationFrame(f); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add(); })()"""


def glide(pg, x, y, sec):
    """1편과 같은 감속 이동."""
    x0, y0 = pos
    n = max(8, int(sec * 60))
    for i in range(1, n + 1):
        e = 1 - (1 - i / n) ** 3
        pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
        time.sleep(sec / n)
    pos[:] = [x, y]


def scroll_to(pg, y, sec):
    pg.evaluate("""([y, ms]) => new Promise(res => { const s = scrollY, t0 = performance.now();
      const f = n => { const p = Math.min(1, (n - t0) / ms), e = p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2;
        scrollTo(0, s + (y - s) * e); p < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); })""", [y, sec * 1000])


def scene(pg, mark):
    pg.goto("https://taekwonworld.net/", wait_until="networkidle", timeout=60000)
    pg.mouse.move(*pos)
    time.sleep(1.0)
    mark("scroll")                       # 1편 양식 화면처럼 내려갔다 올라오기
    scroll_to(pg, 650, 1.4); time.sleep(0.2); scroll_to(pg, 0, 1.1)
    mark("glide")
    b = pg.locator("button:has-text('로그인(관장)')").first.bounding_box()
    glide(pg, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 1.2)
    mark("glide_end")
    time.sleep(0.4)
    pg.mouse.down(); time.sleep(0.07); pg.mouse.up()
    pg.wait_for_url("**/account/login", timeout=15000); pg.wait_for_load_state("networkidle")
    time.sleep(0.6)
    glide(pg, 700, 500, 1.0)
    time.sleep(1.0)                      # 정지 구간 → 기준 사진과 비교
    mark("still")
    time.sleep(0.5)


def run_x11(p):
    """1편 방식 그대로."""
    env = dict(os.environ, DISPLAY=":99")
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", f"{PW}x{PH}x24", "-nocursor"], stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=CHROME, headless=False, env=env,
        no_viewport=True, ignore_default_args=["--enable-automation"],
        args=["--kiosk", "--window-position=0,0", f"--window-size={W},{H}", f"--force-device-scale-factor={SCALE}",
              "--hide-scrollbars", "--no-first-run", "--disable-infobars"])
    ctx.add_init_script(CURSOR); ctx.add_init_script(COUNTER)
    pg = ctx.pages[0]
    pg.goto("about:blank"); time.sleep(0.5)
    cap = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-framerate", str(FPS),
                            "-video_size", f"{PW}x{PH}", "-draw_mouse", "0", "-i", ":99",
                            "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0", str(out / "x11.mkv")],
                           stdin=subprocess.PIPE)
    t0 = time.monotonic(); marks = {}
    scene(pg, lambda k: marks.__setitem__(k, round(time.monotonic() - t0, 3)))
    time.sleep(0.3)
    cap.communicate(b"q", timeout=120)
    pg.screenshot(path=str(out / "x11_still.png"))
    ctx.close(); xvfb.terminate()
    return {"marks": marks}


def run_cdp(p, headed):
    """CDP Page.startScreencast: 화면이 바뀔 때마다 프레임(PNG/JPEG)과 시각을 받는다."""
    xvfb = None
    if headed:
        xvfb = subprocess.Popen(["Xvfb", ":98", "-screen", "0", f"{PW}x{PH}x24", "-nocursor"], stderr=subprocess.DEVNULL)
        time.sleep(1.5)
    if MODE == "cdp-fast":   # 창 없이, 실제 배율(흉내 내기 없음), 프레임은 메모리에만 받아 두고 나중에 저장
        br = p.chromium.launch(executable_path=CHROME, args=[f"--window-size={W},{H}", f"--force-device-scale-factor={SCALE}",
                                                             "--hide-scrollbars"])
        ctx = br.new_context(no_viewport=True)
    elif headed:   # 1편처럼 창 자체를 1.5배로 (흉내 내기 대신 실제 배율)
        br = p.chromium.launch(executable_path=CHROME, headless=False, env=dict(os.environ, DISPLAY=":98"),
                               ignore_default_args=["--enable-automation"],
                               args=["--kiosk", "--window-position=0,0", f"--window-size={W},{H}",
                                     f"--force-device-scale-factor={SCALE}", "--hide-scrollbars", "--disable-infobars"])
        ctx = br.new_context(no_viewport=True)
    else:
        br = p.chromium.launch(executable_path=CHROME, args=["--hide-scrollbars"])
        ctx = br.new_context(viewport={"width": W, "height": H}, device_scale_factor=SCALE)
    ctx.add_init_script(CURSOR); ctx.add_init_script(COUNTER)
    pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg)
    fmt = FMT
    frames, lock = [], threading.Lock()
    fdir = out / f"{TAG}_frames"
    fdir.mkdir(exist_ok=True)
    for f in fdir.glob("*"):
        f.unlink()

    datas = []

    def on_frame(ev):
        cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})   # 응답해야 다음 프레임이 온다
        frames.append(ev["metadata"]["timestamp"])
        datas.append(ev["data"])

    cdp.on("Page.screencastFrame", on_frame)
    params = {"format": fmt, "maxWidth": PW, "maxHeight": PH, "everyNthFrame": 1}
    if fmt == "jpeg":
        params["quality"] = 100
    cdp.send("Page.startScreencast", params)
    t0 = time.monotonic(); wall0 = time.time(); marks = {}
    scene(pg, lambda k: marks.__setitem__(k, round(time.monotonic() - t0, 3)))
    cdp.send("Page.stopScreencast")
    time.sleep(0.5)
    pg.screenshot(path=str(out / f"{TAG}_still.png"))
    br.close()
    for i, d in enumerate(datas):
        (fdir / f"{i:05d}.{fmt}").write_bytes(base64.b64decode(d))
    if xvfb:
        xvfb.terminate()
    # 받은 프레임을 시각대로 일정 프레임 영상(무손실)으로: 프레임마다 다음 프레임까지 그대로 유지
    ts = [t - wall0 for t in frames]
    lst = out / f"{TAG}_list.txt"
    with lst.open("w") as f:
        for i, t in enumerate(ts):
            d = (ts[i + 1] - t) if i + 1 < len(ts) else 0.5
            f.write(f"file '{(fdir / f'{i:05d}.{fmt}').resolve()}'\nduration {max(d, 0.001):.4f}\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps={FPS}", "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0",
                    str(out / f"{TAG}.mkv")], check=True)
    return {"marks": marks, "frame_t": [round(t, 4) for t in ts], "format": fmt}


with sync_playwright() as p:
    info = run_x11(p) if MODE == "x11" else run_cdp(p, MODE == "cdp-head")
(out / f"{TAG}_frames.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print(TAG, info["marks"], len(info.get("frame_t", [])), "frames")

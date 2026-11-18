"""태권월드 1편(관장님 회원가입) 녹화. 나레이션 문장 길이에 맞춰 조작한다.
python record_ep1.py dry   → 리허설(헤드리스, 녹화 없음)
python record_ep1.py rec   → Xvfb 가상 화면 + x11grab 무손실 녹화

안전장치: 가입 양식 화면에서는 xhr/fetch 요청을 전부 막는다 → 문자 발송·중복확인·계정 생성이 실제로 일어나지 않음.
개인정보: 이름·휴대전화·인증번호·생년월일·성별 칸은 처음부터 글자를 흐리게 표시 → 실제 값이 화면에 나오지 않음."""
import json, os, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

MODE = sys.argv[1] if len(sys.argv) > 1 else "dry"
here = Path(__file__).parent
NAR = json.loads((here / "narration.json").read_text(encoding="utf-8"))
DUR = {k: v[2] for k, v in NAR.items()}
SCALE = 1.5                        # CSS 1920x1080 → 화면 2880x1620
GAP = 0.55                         # 문장 사이 쉼

CURSOR = """(() => { const add = () => { if (document.getElementById('__cur')) return; const c = document.createElement('div'); c.id='__cur';
  c.innerHTML = '<svg width="34" height="34" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8 16 L12 24 L15 23 L11 15 L18 15 Z" fill="#111" stroke="#fff" stroke-width="1.6"/></svg>';
  c.style.cssText='position:fixed;left:0;top:0;pointer-events:none;z-index:2147483647;transform:translate(960px,640px)';
  document.documentElement.appendChild(c);
  document.addEventListener('mousemove', e => c.style.transform = `translate(${e.clientX-3}px,${e.clientY-2}px)`, true); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add(); })()"""
# 개인정보 칸은 글자를 투명하게 하고 흐린 그림자만 남긴다 (입력 중에도 실제 값이 보이지 않음)
PRIVACY_CSS = """input[name=last_name], input[name=first_name], input[name=phone_number], input[name=number_by_user]
  { color: transparent !important; text-shadow: 0 0 9px rgba(30,30,30,.75) !important; caret-color: transparent !important; }
  div[role=combobox]:has(+ input[name=dob]), div[role=combobox]:has(+ input[name=sex_code])
  { color: transparent !important; text-shadow: 0 0 9px rgba(30,30,30,.75) !important; }"""

log = {"lines": [], "clicks": [], "spots": [], "marks": {}}
pos = [960.0, 640.0]
t0 = None


def now():
    return time.monotonic() - t0


def glide(pg, x, y, sec):
    x0, y0 = pos
    n = max(8, int(sec * 60))
    for i in range(1, n + 1):
        p = i / n
        e = 1 - (1 - p) ** 3 if p < 1 else 1      # 감속하며 도착 (곧장 가서 부드럽게 멈춤)
        pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
        time.sleep(sec / n)
    pos[:] = [x, y]


def click(pg):
    log["clicks"].append({"t": round(now(), 3), "x": pos[0] * SCALE, "y": pos[1] * SCALE})
    pg.mouse.down(); time.sleep(0.07); pg.mouse.up()


def center(pg, sel):
    b = pg.locator(sel).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, b


def spot(b, start, end, pad=0):
    log["spots"].append({"start": round(start, 3), "end": round(end, 3), "x": (b["x"] - pad) * SCALE,
                         "y": (b["y"] - pad) * SCALE, "w": (b["width"] + 2 * pad) * SCALE, "h": (b["height"] + 2 * pad) * SCALE})


def line(key):
    """나레이션 한 문장 시작. 끝나는 시각을 돌려준다."""
    t = now()
    log["lines"].append({"key": key, "t": round(t, 3)})
    return t + DUR[key]


def wait_until(t):
    d = t - now()
    if d > 0:
        time.sleep(d)


def scroll_to(pg, y, sec=0.9):
    pg.evaluate("""([y, ms]) => new Promise(res => { const s = scrollY, t0 = performance.now();
      const f = n => { const p = Math.min(1, (n - t0) / ms), e = p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2;
        scrollTo(0, s + (y - s) * e); p < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); })""", [y, sec * 1000])


def act_click(pg, sel, key, lead=0.35, pad=8):
    """문장을 시작하고, 버튼으로 곧장 이동 → 잠깐 멈춤 → 문장 끝 무렵 클릭. 그동안 버튼 주변만 밝게."""
    end = line(key)
    x, y, b = center(pg, sel)
    s0 = now()
    move = max(0.6, min(1.2, DUR[key] * 0.35))
    time.sleep(max(0.0, DUR[key] - move - lead - 0.5) * 0.4)
    glide(pg, x, y, move)
    wait_until(end - lead)
    click(pg)
    spot(b, s0, now() + 0.4, pad)
    return end


def typ(pg, sel, text, delay=0.09):
    pg.locator(sel).first.click()
    log["clicks"].append({"t": round(now(), 3), "x": pos[0] * SCALE, "y": pos[1] * SCALE})
    for ch in text:
        pg.keyboard.type(ch)
        time.sleep(delay)


def pick(pg, combo_idx, option_text=None, option_idx=None):
    """MUI 선택 상자: 열고 → 항목 클릭."""
    cb = pg.locator("div[role=combobox]").nth(combo_idx)
    x, y, _ = (lambda b: (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, b))(cb.bounding_box())
    glide(pg, x, y, 0.35); click(pg)
    time.sleep(0.35)
    opt = pg.get_by_role("option", name=option_text, exact=True) if option_text else pg.get_by_role("option").nth(option_idx)
    opt.scroll_into_view_if_needed()
    ob = opt.bounding_box()
    glide(pg, ob["x"] + min(60, ob["width"] / 2), ob["y"] + ob["height"] / 2, 0.3); click(pg)
    time.sleep(0.3)


def scenario(pg):
    # 녹화 동기 표시: 화면을 0.3초 검게 → 영상에서 이 순간을 찾아 시각을 맞춘다
    pg.goto("https://taekwonworld.net/", wait_until="networkidle", timeout=60000)
    pg.mouse.move(*pos)
    time.sleep(0.8)
    pg.evaluate("() => { const d = document.createElement('div'); d.id='__sync'; d.style.cssText='position:fixed;inset:0;background:#000;z-index:2147483646'; document.body.appendChild(d); }")
    log["marks"]["sync"] = round(now(), 3)
    time.sleep(0.3)
    pg.evaluate("() => document.getElementById('__sync').remove()")
    time.sleep(0.8)
    log["marks"]["body_start"] = round(now(), 3)

    # ── 1단계: 가입 화면 찾기 ──
    log["marks"]["step1"] = round(now(), 3)
    end = act_click(pg, "button:has-text('로그인(관장)')", "S1")
    pg.wait_for_url("**/account/login", timeout=15000); pg.wait_for_load_state("networkidle")
    wait_until(end + GAP)
    end = act_click(pg, "button:has-text('회원가입')", "S2")
    pg.wait_for_url("**/account/sign", timeout=15000); pg.wait_for_load_state("networkidle")
    wait_until(end + GAP)
    end = line("S3")
    b = pg.get_by_text("관장님", exact=True).first.bounding_box()
    card = pg.locator("h1:has-text('관장님')").first.locator("xpath=ancestor::div[2]").bounding_box() or b
    time.sleep(DUR["S3"] * 0.45)
    s0 = now()
    glide(pg, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2 + 60, 0.8)
    wait_until(end - 0.35)
    # 가입 양식 화면부터는 서버 요청 차단 (문자 발송·중복확인·계정 생성 방지)
    pg.route("**/*", lambda r: r.abort() if r.request.resource_type in ("xhr", "fetch") and "/account/sign/kwanjang" in (pg.url or "") else r.continue_())
    click(pg); spot(card, s0, now() + 0.4, 6)
    pg.wait_for_url("**/account/sign/kwanjang", timeout=15000)
    pg.add_style_tag(content=PRIVACY_CSS)
    pg.wait_for_selector("input[name=username]")
    time.sleep(0.4)
    log["marks"]["form_ready"] = round(now(), 3)
    wait_until(end + GAP)

    # ── 2단계: 정보 입력하기 ──
    log["marks"]["step2"] = round(now(), 3)
    end = line("F1")
    scroll_to(pg, 650, 1.4); time.sleep(0.2); scroll_to(pg, 0, 1.1)
    wait_until(end + GAP * 0.6)
    # 아이디 + 중복확인
    end = line("F2")
    x, y, b = center(pg, "input[name=username]")
    s0 = now(); glide(pg, x - 150, y, 0.7)
    typ(pg, "input[name=username]", "taekwon_demo")
    x2, y2, b2 = center(pg, "button:has-text('중복확인')")
    glide(pg, x2, y2, 0.5); wait_until(end - 0.3); click(pg)
    spot({"x": b["x"], "y": b["y"], "width": b2["x"] + b2["width"] - b["x"], "height": b["height"]}, s0, now() + 0.4, 8)
    wait_until(end + GAP)
    # 비밀번호 두 번
    end = line("F3")
    x, y, b = center(pg, "input[name=password]")
    s0 = now(); glide(pg, x - 150, y, 0.5)
    typ(pg, "input[name=password]", "demo1234!", 0.06)
    x, y, b2 = center(pg, "input[name=chk_password]")
    glide(pg, x - 150, y, 0.4)
    typ(pg, "input[name=chk_password]", "demo1234!", 0.06)
    spot({"x": b["x"], "y": b["y"], "width": b["width"], "height": b2["y"] + b2["height"] - b["y"]}, s0, now() + 0.3, 8)
    wait_until(end + GAP)
    # 이름 (흐림)
    end = line("F4")
    scroll_to(pg, 260, 0.8)
    x, y, b = center(pg, "input[name=last_name]")
    s0 = now(); glide(pg, x - 60, y, 0.5)
    typ(pg, "input[name=last_name]", "김", 0.12)
    x, y, b2 = center(pg, "input[name=first_name]")
    glide(pg, x - 60, y, 0.4)
    typ(pg, "input[name=first_name]", "태권", 0.12)
    spot({"x": b["x"], "y": b["y"], "width": b2["x"] + b2["width"] - b["x"], "height": b["height"]}, s0, now() + 0.3, 8)
    wait_until(end + GAP)
    # 휴대전화 + 인증요청 (흐림, 요청은 차단됨)
    end = line("F5")
    x, y, b = center(pg, "input[name=phone_number]")
    s0 = now(); glide(pg, x - 120, y, 0.5)
    typ(pg, "input[name=phone_number]", "01000000000", 0.07)
    x2, y2, b2 = center(pg, "button:has-text('인증요청')")
    glide(pg, x2, y2, 0.45); wait_until(end - 0.3); click(pg)
    spot({"x": b["x"] - 108, "y": b["y"], "width": b2["x"] + b2["width"] - b["x"] + 108, "height": b["height"]}, s0, now() + 0.4, 8)
    log["marks"]["sms_request"] = round(now(), 3)
    wait_until(end + GAP)
    # 인증번호 + 인증확인
    end = line("F6")
    x, y, b = center(pg, "input[name=number_by_user]")
    s0 = now(); glide(pg, x - 150, y, 0.5)
    typ(pg, "input[name=number_by_user]", "000000", 0.1)
    x2, y2, b2 = center(pg, "button:has-text('인증확인')")
    glide(pg, x2, y2, 0.45); wait_until(end - 0.3); click(pg)
    spot({"x": b["x"], "y": b["y"], "width": b2["x"] + b2["width"] - b["x"], "height": b["height"]}, s0, now() + 0.4, 8)
    wait_until(end + GAP)
    end = line("F7")                                   # 안심 문장: 화면은 그대로, 말풍선 자막
    log["marks"]["reassure"] = round(now(), 3)
    wait_until(end + GAP)
    # 생년월일 · 성별 · 단
    end = line("F8")
    scroll_to(pg, 600, 0.9)
    s0 = now()
    combos = pg.locator("div[role=combobox]")
    b0 = combos.nth(2).bounding_box()
    pick(pg, 2, option_idx=25)      # 연도 (흐림)
    pick(pg, 3, option_idx=4)       # 월
    pick(pg, 4, option_idx=14)      # 일
    pick(pg, 5, option_idx=0)       # 성별 (흐림)
    pick(pg, 6, option_idx=5)       # 단
    b6 = combos.nth(6).bounding_box()
    spot({"x": b0["x"], "y": b0["y"], "width": 500, "height": b6["y"] + b6["height"] - b0["y"]}, s0, now() + 0.3, 10)
    wait_until(end + GAP)

    # ── 3단계: 약관 동의하고 등록 ──
    log["marks"]["step3"] = round(now(), 3)
    end = line("T1")
    scroll_to(pg, 10_000, 0.9)
    box = pg.locator("input[type=checkbox]").first.locator("xpath=ancestor::div[3]").bounding_box()
    x, y, b = center(pg, "input[type=checkbox] >> nth=0")
    s0 = now(); glide(pg, x, y, 0.8)
    wait_until(end - 1.6); click(pg)
    spot(box, s0, now() + 1.2, 6)
    wait_until(end + GAP)
    end = act_click(pg, "button:has-text('등록')", "T2", lead=0.6)
    log["marks"]["submit"] = round(now(), 3)
    time.sleep(0.9)
    log["marks"]["body_end"] = round(now(), 3)


def main():
    global t0
    with sync_playwright() as p:
        if MODE == "rec":
            import tempfile
            env = dict(os.environ, DISPLAY=":99")
            xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "2880x1620x24", "-nocursor"], stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            # 기본 창을 그대로 써야 전체 화면(kiosk)이 적용된다. 창 크기는 CSS 픽셀 기준(1920x1080 × 1.5배 = 2880x1620)
            ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path="/opt/pw-browsers/chromium",
                headless=False, env=env, no_viewport=True, ignore_default_args=["--enable-automation"],
                args=["--kiosk", "--window-position=0,0", "--window-size=1920,1080", "--force-device-scale-factor=1.5",
                      "--hide-scrollbars", "--no-first-run", "--disable-infobars"])
            b = ctx
        else:
            b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
            ctx = b.new_context(viewport={"width": 1920, "height": 1080})
        ctx.add_init_script(CURSOR)
        pg = ctx.pages[0] if MODE == "rec" else ctx.new_page()
        pg.on("dialog", lambda d: d.dismiss())
        cap = None
        if MODE == "rec":
            pg.goto("about:blank"); time.sleep(0.5)
            cap = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-framerate", "30",
                                    "-video_size", "2880x1620", "-draw_mouse", "0", "-i", ":99",
                                    "-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0", str(here / "cap.mkv")],
                                   stdin=subprocess.PIPE)
        t0 = time.monotonic()
        try:
            scenario(pg)
        finally:
            if cap:
                time.sleep(0.5)
                cap.communicate(b"q", timeout=60)
            (here / f"log_{MODE}.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
            pg.screenshot(path=str(here / f"last_{MODE}.png"))
            b.close()
            if MODE == "rec":
                xvfb.terminate()
    print(json.dumps(log["marks"]), len(log["clicks"]), "clicks", len(log["spots"]), "spots")


main()

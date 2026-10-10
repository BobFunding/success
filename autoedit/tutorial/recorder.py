"""자동 녹화: 장면 표대로 사이트를 조작하며 찍는다 (tutorials/ep1/record_ep1.py 일반화).

나레이션 문장 길이에 맞춰 커서를 움직이고, 문장 끝 무렵에 누른다. 클릭 시각·좌표, 밝게 할 곳, 문장 시작 시각을
기록해 편집(screenfx)이 판단 없이 계산만 하게 한다. 박자 계산은 1편과 같아야 한다(1편 재현 검사).

mode="dry": 리허설(창 없이, 녹화 없이) — 모든 누를 곳을 찾는지 확인
mode="rec": 녹화
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path

from .capture import open_capture
from .scenario import Scenario, Scene

CHROME = "/opt/pw-browsers/chromium"
W, H, SCALE = 1920, 1080, 1.5          # CSS 1920x1080 × 1.5 = 화면 2880x1620 (1편)

CURSOR = """(() => { const add = () => { if (document.getElementById('__cur')) return; const c = document.createElement('div'); c.id='__cur';
  c.innerHTML = '<svg width="34" height="34" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8 16 L12 24 L15 23 L11 15 L18 15 Z" fill="#111" stroke="#fff" stroke-width="1.6"/></svg>';
  c.style.cssText='position:fixed;left:0;top:0;pointer-events:none;z-index:2147483647;transform:translate(960px,640px)';
  document.documentElement.appendChild(c);
  document.addEventListener('mousemove', e => c.style.transform = `translate(${e.clientX-3}px,${e.clientY-2}px)`, true); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add(); })()"""

BLUR = "color: transparent !important; text-shadow: 0 0 9px rgba(30,30,30,.75) !important;"


def privacy_css(fields: list[str]) -> str:
    """개인정보 칸: 글자를 투명하게 하고 흐린 그림자만 남긴다(입력 중에도 실제 값이 보이지 않음).
    MUI 선택 상자처럼 값이 옆 요소에 보이는 경우도 함께 가린다."""
    if not fields:
        return ""
    inputs = ", ".join(fields)
    combos = ", ".join(f"div[role=combobox]:has(+ {f})" for f in fields)
    return (f"{inputs} {{ {BLUR} caret-color: transparent !important; }}\n"
            f"{combos} {{ {BLUR} }}")


def style_script(css: str) -> str:
    """모든 화면에 처음부터 CSS 를 넣는 init script."""
    return ("(() => { const css = %s; const add = () => { if (document.getElementById('__priv')) return;"
            " const s = document.createElement('style'); s.id = '__priv'; s.textContent = css;"
            " (document.head || document.documentElement).appendChild(s); };"
            " if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add(); })()"
            % json.dumps(css))


def is_selector(s: str) -> bool:
    """'button:has-text(...)', 'input[name=id]', '#id', 'text="..."', 'css=...' 는 선택자, '로그인(관장)' 같은 건 보이는 글자."""
    return bool(re.search(r"[\[\]#=>'\"]|^(css|text|xpath|internal):|^[a-z]+(\.[\w-]+)+$|:has|:nth|^[a-z]+$", s))


class SceneError(RuntimeError):
    """사람이 읽는 오류: 몇 번 장면의 무엇을 못 찾았는지."""

    def __init__(self, scene: Scene, what: str, detail: str = ""):
        self.scene = scene
        self.detail = detail
        name = scene.label or what
        if detail and ("않았어요" in detail or "없어요" in detail):
            msg = f"{scene.no}번 장면 '{name}': {detail}."
        else:
            msg = (f"{scene.no}번 장면의 '{name}'을(를) 찾지 못했어요. 화면 글자가 바뀌었는지 확인해 주세요."
                   + (f" ({detail})" if re.search("[가-힣]", detail) else ""))   # 기술 용어(오류 이름)는 보여 주지 않음
        super().__init__(msg)


class Recorder:
    def __init__(self, sc: Scenario, durations: dict[str, float], log=print):
        self.sc = sc
        self.dur = durations
        self.say = log
        self.log = {"lines": [], "clicks": [], "spots": [], "marks": {}}
        self.pos = [960.0, 640.0]
        self.t0 = 0.0
        self.pg = None
        self.scene: Scene | None = None
        self.blocking = False
        self.mode = "dry"

    def block_requests(self) -> None:
        """저장·발송 요청(xhr/fetch) 차단을 켠다(안전 규칙). 차단 주소 화면에서만 막는다.
        1편처럼 그 화면으로 넘어가기 직전에 켠다 — 처음부터 켜면 모든 요청이 거쳐 가서 화면이 늦게 뜬다."""
        blk = self.sc.block_requests
        if not blk or self.blocking:
            return
        pg = self.pg
        pg.route("**/*", lambda r: r.abort() if r.request.resource_type in ("xhr", "fetch")
                 and blk in (pg.url or "") else r.continue_())
        self.blocking = True

    # ── 기본 동작 (1편과 같은 계산) ──
    def now(self) -> float:
        return time.monotonic() - self.t0

    def mark(self, k: str) -> None:
        self.log["marks"][k] = round(self.now(), 3)

    def glide(self, x, y, sec):
        x0, y0 = self.pos
        n = max(8, int(sec * 60))
        for i in range(1, n + 1):
            p = i / n
            e = 1 - (1 - p) ** 3 if p < 1 else 1      # 감속하며 도착 (곧장 가서 부드럽게 멈춤)
            self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            time.sleep(sec / n)
        self.pos[:] = [x, y]

    def click(self):
        self.log["clicks"].append({"t": round(self.now(), 3), "x": self.pos[0] * SCALE, "y": self.pos[1] * SCALE})
        self.pg.mouse.down(); time.sleep(0.07); self.pg.mouse.up()

    def locate(self, target: str):
        """누를 곳 찾기: 선택자면 그대로, 보이는 글자면 버튼 → 링크 → 라벨 → 안내 글씨 → 글자 순서로."""
        if is_selector(target):
            return self.pg.locator(target).first
        pg = self.pg
        for loc in (pg.get_by_role("button", name=target, exact=True), pg.get_by_role("link", name=target, exact=True),
                    pg.get_by_label(target, exact=True), pg.get_by_placeholder(target, exact=True),
                    pg.get_by_text(target, exact=True)):
            try:
                if loc.count():
                    return loc.first
            except Exception:
                pass
        return pg.get_by_text(target).first

    def box(self, sel: str, what: str = "") -> dict:
        b, err = None, ""
        try:
            b = self.locate(sel).bounding_box(timeout=10000)
        except Exception as e:                       # 시간 초과 등
            err = type(e).__name__
        if not b and self.scene and self.scene.label and self.scene.label != sel and what == self.scene.label:
            try:                                     # 선택자가 바뀐 사이트: 보이는 글자로 한 번 더
                b = self.locate(self.scene.label).bounding_box(timeout=3000)
            except Exception:
                pass
        if not b:
            raise SceneError(self.scene, what or sel, err or "화면에 보이지 않음")
        return b

    def center(self, sel: str, what: str = ""):
        b = self.box(sel, what)
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, b

    def spot(self, b, start, end, pad=0):
        self.log["spots"].append({"start": round(start, 3), "end": round(end, 3), "x": (b["x"] - pad) * SCALE,
                                  "y": (b["y"] - pad) * SCALE, "w": (b["width"] + 2 * pad) * SCALE,
                                  "h": (b["height"] + 2 * pad) * SCALE})

    def line(self, key: str) -> float:
        """나레이션 한 문장 시작. 끝나는 시각을 돌려준다."""
        t = self.now()
        self.log["lines"].append({"key": key, "t": round(t, 3)})
        return t + self.dur[key]

    def wait_until(self, t):
        d = t - self.now()
        if d > 0:
            time.sleep(d)

    def scroll_to(self, y, sec=0.9):
        self.pg.evaluate("""([y, ms]) => new Promise(res => { const s = scrollY, t0 = performance.now();
          const f = n => { const p = Math.min(1, (n - t0) / ms), e = p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2;
            scrollTo(0, s + (y - s) * e); p < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); })""",
                         [y, sec * 1000])

    def typ(self, sel, text, delay):
        """커서가 있는 자리에서 칸을 누르고 한 글자씩 적는다.
        (1편은 locator.click 이라 실제 마우스가 칸 가운데로 옮겨져 그려 둔 커서가 순간 이동했다 — 2026-10-10 사용자 승인으로 고침)"""
        loc = self.locate(sel)
        b = self.box(sel)
        x, y = self.pos
        if not (b["x"] + 4 <= x <= b["x"] + b["width"] - 4 and b["y"] + 4 <= y <= b["y"] + b["height"] - 4):
            # 커서가 칸 밖이면 칸 안쪽 가장 가까운 곳으로 살짝 옮긴다
            self.glide(min(max(x, b["x"] + 12), b["x"] + b["width"] - 12), b["y"] + b["height"] / 2, 0.15)
        self.log["clicks"].append({"t": round(self.now(), 3), "x": self.pos[0] * SCALE, "y": self.pos[1] * SCALE})
        self.pg.mouse.down(); self.pg.mouse.up()
        if not loc.evaluate("e => e === document.activeElement || e.contains(document.activeElement)"):
            loc.focus()                              # 다른 것이 덮고 있어 클릭이 안 먹으면 직접 맞춘다
        for ch in text:
            self.pg.keyboard.type(ch)
            time.sleep(delay)
        if self.mode == "dry" and text and not loc.input_value():   # 사이트가 모양을 바꿔 넣을 수 있어 비었는지만 본다
            raise SceneError(self.scene, sel, "적은 글자가 칸에 들어가지 않았어요")

    def pick(self, box_idx, option_idx=None, option_text=None):
        """선택 상자: 열고 → 항목 클릭."""
        cb = self.pg.locator("div[role=combobox]").nth(box_idx)
        b = cb.bounding_box()
        if not b:
            raise SceneError(self.scene, f"{box_idx + 1}번째 선택 상자")
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.35); self.click()
        time.sleep(0.35)
        opt = (self.pg.get_by_role("option", name=option_text, exact=True) if option_text
               else self.pg.get_by_role("option").nth(option_idx))
        opt.scroll_into_view_if_needed()
        ob = opt.bounding_box()
        self.glide(ob["x"] + min(60, ob["width"] / 2), ob["y"] + ob["height"] / 2, 0.3); self.click()
        time.sleep(0.3)

    def pick_native(self, p) -> None:
        """기본 <select>: 상자로 가서 누르고 항목을 고른다(펼친 목록은 운영체제가 그려서 바로 고름)."""
        x, y, _ = self.center(p.target, self.scene.label if self.scene else "")
        self.glide(x, y, 0.45); self.click()
        loc = self.locate(p.target)
        time.sleep(0.25)
        try:
            if p.text:
                loc.select_option(label=p.text, timeout=5000)
            else:
                loc.select_option(index=int(p.index or 0), timeout=5000)
        except Exception:
            raise SceneError(self.scene, p.text or p.target, "목록에 그 항목이 없어요") from None
        self.pg.keyboard.press("Escape")
        time.sleep(0.3)

    # ── 장면 ──
    def do_click(self, s: Scene, end: float) -> None:
        """누를 곳으로 곧장 이동 → 잠깐 멈춤 → 문장 끝 무렵 클릭. 그동안 누를 곳 주변만 밝게."""
        d = self.dur[s.key]
        if s.scroll_first:
            self.scroll_to(*s.scroll_first)
        x, y, b = self.center(s.target, s.label)
        sb = self.box(s.spot_target, s.label) if s.spot_target else b
        move = s.move if s.move is not None else max(0.6, min(1.2, d * 0.35))
        s0 = self.now()
        pre = d * s.pre_wait if s.pre_wait is not None else max(0.0, d - move - s.lead - 0.5) * 0.4
        time.sleep(pre)
        if s.spot_from == "이동":
            s0 = self.now()
        self.glide(x + s.offset[0], y + s.offset[1], move)
        self.wait_until(end - s.lead)
        if self.sc.block_requests and self.sc.block_requests.strip("*") in s.next_url:
            self.block_requests()
        self.click()
        self.spot(sb, s0, self.now() + (s.spot_hold if s.spot_hold is not None else 0.4), s.spot_pad)

    def do_type(self, s: Scene, end: float) -> None:
        if s.scroll_first:
            self.scroll_to(*s.scroll_first)
        boxes, s0 = [], None
        for f in s.fields:
            x, y, b = self.center(f.target, s.label)
            if s0 is None:
                s0 = self.now()
            self.glide(x + f.approach, y, f.move)
            value = f.value
            if value.startswith("@보관함"):              # 비밀번호: 장면 표에는 없고 PC 안 보관함에서
                from . import secrets
                value = secrets.get(self.sc.file_name)
            self.typ(f.target, value, f.delay)
            boxes.append(b)
        if s.button:
            x2, y2, b2 = self.center(s.button, s.label)
            self.glide(x2, y2, s.button_move); self.wait_until(end - 0.3); self.click()
            boxes.append(b2)
        hold = s.spot_hold if s.spot_hold is not None else (0.4 if s.button else 0.3)
        self.spot(self._union(boxes, s), s0, self.now() + hold, s.spot_pad)

    def do_pick(self, s: Scene, end: float) -> None:
        if s.scroll_first:
            self.scroll_to(*s.scroll_first)
        s0 = self.now()
        combos = self.pg.locator("div[role=combobox]")
        where = lambda p: self.box(p.target, s.label) if p.target else combos.nth(p.box).bounding_box()
        first = where(s.picks[0])
        for p in s.picks:
            if p.target:
                self.pick_native(p)
            else:
                self.pick(p.box, p.index, p.text)
        last = where(s.picks[-1])
        hold = s.spot_hold if s.spot_hold is not None else 0.3
        self.spot(self._union([first, last], s), s0, self.now() + hold, s.spot_pad)

    @staticmethod
    def _union(boxes: list[dict], s: Scene) -> dict:
        """여러 칸을 하나의 밝은 곳으로. 1편 계산 그대로(가로: 첫 칸 높이, 세로: 첫 칸 너비)."""
        a, z = boxes[0], boxes[-1]
        if s.spot_shape == "세로":
            u = {"x": a["x"], "y": a["y"], "width": a["width"], "height": z["y"] + z["height"] - a["y"]}
        else:
            u = {"x": a["x"], "y": a["y"], "width": z["x"] + z["width"] - a["x"], "height": a["height"]}
        if s.spot_width is not None:
            u["width"] = float(s.spot_width)
        if s.spot_extend_left:
            u["x"] -= s.spot_extend_left
            u["width"] += s.spot_extend_left
        return u

    def run_scene(self, s: Scene, last: bool) -> None:
        self.scene = s
        end = self.line(s.key)
        if s.bubble:
            self.mark(f"bubble_{s.key}")
        if s.action in ("클릭", "체크"):
            self.do_click(s, end)
            try:
                if s.next_url:
                    self.pg.wait_for_url(s.next_url, timeout=15000)
                    if not s.wait_for:
                        self.pg.wait_for_load_state("networkidle")
                if s.wait_for:
                    self.pg.wait_for_selector(s.wait_for)
                    time.sleep(0.4)
            except SceneError:
                raise
            except Exception:
                raise SceneError(s, s.label or s.target, "누른 뒤 다음 화면으로 넘어가지 않았어요") from None
        elif s.action == "입력":
            self.do_type(s, end)
        elif s.action == "선택":
            self.do_pick(s, end)
        elif s.action == "스크롤":
            for kind, a, b in s.scrolls:
                if kind == "대기":
                    time.sleep(a)
                else:
                    self.scroll_to(a, b)
        # 보여주기·대기: 화면은 그대로, 문장만
        if last:
            time.sleep(self.sc.end_hold)
        else:
            self.wait_until(end + s.gap)

    def scenario(self) -> None:
        pg = self.pg
        # 녹화 동기 표시: 화면을 0.3초 검게 → 영상에서 이 순간을 찾아 시각을 맞춘다
        pg.goto(self.sc.url, wait_until="networkidle", timeout=60000)
        pg.mouse.move(*self.pos)
        time.sleep(0.8)
        pg.evaluate("() => { const d = document.createElement('div'); d.id='__sync'; d.style.cssText='position:fixed;inset:0;background:#000;z-index:2147483646'; document.body.appendChild(d); }")
        self.mark("sync")
        time.sleep(0.3)
        pg.evaluate("() => document.getElementById('__sync').remove()")
        time.sleep(0.8)
        self.mark("body_start")
        step = 0
        for i, s in enumerate(self.sc.scenes):
            if s.step != step:
                step = s.step
                self.mark(f"step{step}")
            self.run_scene(s, i == len(self.sc.scenes) - 1)
        self.mark("body_end")

    # ── 실행 ──
    def run(self, mode: str, out_dir: Path) -> dict:
        from playwright.sync_api import sync_playwright
        self.mode = mode
        out_dir.mkdir(parents=True, exist_ok=True)
        cap = None
        with sync_playwright() as p:
            if mode == "rec":
                cap = open_capture(int(W * SCALE), int(H * SCALE), 30)
                # 기본 창을 그대로 써야 전체 화면(kiosk)이 적용된다. 창 크기는 CSS 픽셀 기준
                ctx = p.chromium.launch_persistent_context(
                    tempfile.mkdtemp(), executable_path=CHROME, headless=False, env=cap.env, no_viewport=True,
                    ignore_default_args=["--enable-automation"],
                    args=["--kiosk", "--window-position=0,0", f"--window-size={W},{H}",
                          f"--force-device-scale-factor={SCALE}", "--hide-scrollbars", "--no-first-run",
                          "--disable-infobars"])
                br = ctx
            else:
                br = p.chromium.launch(executable_path=CHROME)
                ctx = br.new_context(viewport={"width": W, "height": H})
            ctx.add_init_script(CURSOR)
            css = privacy_css(self.sc.privacy_fields)
            if css:
                ctx.add_init_script(style_script(css))
            pg = ctx.pages[0] if mode == "rec" else ctx.new_page()
            self.pg = pg
            pg.on("dialog", lambda d: d.dismiss())
            if self.sc.block_requests:
                if self.sc.block_requests in self.sc.url:
                    self.block_requests()
                # 장면 표에 적지 않은 길로 차단 화면에 들어가도 바로 켠다
                pg.on("framenavigated", lambda f: f == pg.main_frame and self.sc.block_requests in f.url
                      and self.block_requests())
            if mode == "rec":
                pg.goto("about:blank"); time.sleep(0.5)
                cap.start(out_dir / "cap.mkv")
            self.t0 = time.monotonic()
            try:
                self.scenario()
            finally:
                if cap:
                    time.sleep(0.5)
                    cap.stop()
                (out_dir / f"log_{mode}.json").write_text(json.dumps(self.log, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
                try:
                    pg.screenshot(path=str(out_dir / f"last_{mode}.png"))
                finally:
                    br.close()
                    if cap:
                        cap.close()
        self.say(f"[녹화:{mode}] 클릭 {len(self.log['clicks'])}번, 밝게 {len(self.log['spots'])}곳, "
                 f"{self.log['marks'].get('body_end', 0) - self.log['marks'].get('body_start', 0):.1f}초")
        return self.log

"""2편 만들기: 튜토리얼 메이커 엔진 + 이 편만의 동작.
사용: TW_DEMO_ID=.. TUTORIAL_SECRET=.. python run_ep2.py check|make [작업폴더]
- 파일 올리기(사업자 등록증·로고): 파일 선택 창을 가로채서 샘플 파일을 넣는다(서버로 보내지 않음).
- 주소 검색: 카카오 우편번호 창(iframe) 안에서 검색하고 결과를 누른다. iframe 위에서도 커서가 보이게 직접 옮긴다.
- 등록: 도장 등록 화면에서는 태권월드 서버 요청과 모든 쓰기 요청을 막은 채 누르고, 도장 목록으로 넘어간다(실제 등록 없음).
- 흐림: 다른 도장 카드 전체, 태권월드 카드의 전화번호·주소, 주소 검색 창의 주소, 첫 화면의 차량 번호·수련생 이름.
"""
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # 저장소 맨 위
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from autoedit.tutorial import maker, scenario as S          # noqa: E402
from autoedit.tutorial.recorder import Recorder, SceneError, style_script, BLUR  # noqa: E402

HERE = Path(__file__).resolve().parent
CERT = HERE / "sample_business_cert.png"
LOGO = HERE / "logo.png"
SELECT_URL = "https://taekwonworld.net/dojang/select"

EXTRA_CSS = f"""
.__tm_other p, .__tm_other .css-8erkb0 > div {{ {BLUR} }}
.__tm_keep .css-8erkb0:nth-child(-n+3) > p {{ {BLUR} }}
input[placeholder="파일을 업로드 해주세요."] {{ {BLUR} }}
#region_name, .tf_keyword, .txt_addr, .link_post, .txt_postcode, .num_post, .list_post_item {{ {BLUR} }}
.__tm_blur {{ {BLUR} }}
"""

# 첫 화면: 차량 번호, 사진 옆 수련생 이름을 흐리게(글자 모양으로 찾음)
BLUR_JS = r"""(() => {
  const plate = /^\d{1,3}\s?[가-힣]\s?\d{4}$/;
  const phone = /\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{4}/;
  const keep = new Set(['수업전','출석 수','미출석 수','미출석 수련생','미운행','운행중','오전차량','오후차량','차량 현황',
    '홈','대시보드','초대장','도장 관리','수련생','출결','납부','승급','헬스케어','체력평가','앱','도장 홈페이지','알림']);
  const cards = () => {               // 도장 목록: '태권월드 태권도장' 카드 하나만 남기고 나머지 카드는 전부 흐림
    let kept = false;
    for (const c of document.querySelectorAll('div[slide]')) {
      const title = (c.querySelector('p') || {}).innerText || '';
      if (!kept && title.trim() === '태권월드 태권도장') { c.classList.add('__tm_keep'); c.classList.remove('__tm_other'); kept = true; }
      else { c.classList.add('__tm_other'); c.classList.remove('__tm_keep'); }
    }
  };
  const run = () => {
    if (/\/dojang\/select/.test(location.pathname)) return cards();
    if (!/\/home|\/dashboard/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('p, span, div, h6, h5')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!t || keep.has(t)) continue;
      let hit = plate.test(t) || phone.test(t);
      if (!hit && /^[가-힣]{2,4}$/.test(t)) {
        for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
          if (p.querySelector('img') && !p.closest('nav, aside, .MuiDrawer-root')) { hit = true; break; }
      }
      if (hit) e.classList.add('__tm_blur');
    }
  };
  setInterval(run, 150);
})()"""


class Ep2Recorder(Recorder):
    iframe_cursor = False

    # 도장 등록 화면: 태권월드 서버로 가는 xhr/fetch 전부 + 어디로든 가는 쓰기 요청을 막는다.
    # (카카오 주소 검색은 GET 이라 통과)
    def block_requests(self) -> None:
        if not self.sc.block_list or self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            on = self.blocked(pg.url or "")
            host = urlparse(q.url).hostname or ""
            tw = (host.endswith("taekwonworld.net") or host.endswith("taekwonworld.pe.kr")
                  or host.startswith("tk-world.s3")) and q.resource_type in ("xhr", "fetch")
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            if on and write:                       # 저장은 쓰기 요청(POST/PUT/PATCH/DELETE) — 읽기는 통과(주소 검색 창이 필요로 함)
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
            else:
                r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def sleep(self, d: float) -> None:
        """기다리는 동안에도 브라우저 연락(요청 차단 처리)이 멈추지 않게 wait_for_timeout 으로 기다린다."""
        if d <= 0:
            return
        if self.frames or self.pg is None:
            return super().sleep(d)
        self.pg.wait_for_timeout(d * 1000)

    def glide(self, x, y, sec):
        if not self.iframe_cursor:
            return super().glide(x, y, sec)
        x0, y0 = self.pos
        n = max(8, int(sec * (30 if self.frames else 60)))
        for i in range(1, n + 1):
            p = i / n
            e = 1 - (1 - p) ** 3 if p < 1 else 1
            cx, cy = x0 + (x - x0) * e, y0 + (y - y0) * e
            self.pg.mouse.move(cx, cy)
            self.pg.evaluate("([x,y]) => { const c = document.getElementById('__cur'); if (c) c.style.transform = `translate(${x-3}px,${y-2}px)`; }", [cx, cy])
            self.sleep(sec / n)
        self.pos[:] = [x, y]

    def scenario(self) -> None:
        self._con = []
        self.pg.on("console", lambda m: m.type in ("error", "warning") and self._con.append(m.text[:150]))
        self.pg.on("requestfailed", lambda r: ("daum" in r.url or "kakao" in r.url) and self._con.append("FAIL " + r.url[:90] + " " + str(r.failure)))
        self.pg.add_init_script(style_script(EXTRA_CSS).replace("__priv", "__priv_ep2"))
        self.pg.add_init_script(BLUR_JS)
        super().scenario()

    @staticmethod
    def rect(x, y, w, h):
        return {"x": x, "y": y, "width": w, "height": h}

    def run_scene(self, s, last):
        if s.key == "L3":                          # 로그인 뒤 도장 목록이 다 뜬 다음에 문장을 시작
            self.pg.locator("text=관리하러 가기").first.wait_for(timeout=30000)
            self.sleep(0.4)
        h = getattr(self, "do_" + s.key, None)
        if h is None:
            return super().run_scene(s, last)
        self.scene = s
        end = self.line(s.key)
        if s.bubble:
            self.mark(f"bubble_{s.key}")
        try:
            h(s, end)
        except SceneError:
            raise
        except Exception as e:
            self.say("[디버그] " + str(e)[:300]); raise SceneError(s, s.label, f"멈췄어요 ({type(e).__name__})") from None
        self.wait_until(end + s.gap)

    # ── 공통: 버튼으로 가서 문장 끝 무렵 누른다 ──
    def approach(self, sel, end, frac=0.3, move=0.8):
        x, y, b = self.center(sel, self.scene.label)
        s0 = self.now()
        self.sleep(max(0.0, (self.dur[self.scene.key] - move - 0.8) * frac))
        self.glide(x, y, move)
        return s0, b

    def upload(self, sel, path, end):
        with self.pg.expect_file_chooser(timeout=10000) as fc:
            self.wait_until(end - 0.35)
            self.click()
        fc.value.set_files(str(path))
        self.sleep(0.5)

    def do_R1(self, s, end):                       # 사업자 등록증
        btn = "button:has-text('파일 업로드')"
        s0, b = self.approach(btn, end)
        inp = self.box("input[placeholder='파일을 업로드 해주세요.']", s.label)
        self.upload(btn, CERT, end)
        u = self.rect(inp["x"], inp["y"], b["x"] + b["width"] - inp["x"], b["height"])
        self.spot(u, s0, self.now() + 0.8, 8)

    def do_R2(self, s, end):                       # 도장 로고
        btn = "button:has-text('사진 올리기')"
        s0, b = self.approach(btn, end)
        self.upload(btn, LOGO, end)
        self.spot(self.rect(b["x"], b["y"] - 67, 650, 180), s0, self.now() + 1.0, 8)

    def do_R3(self, s, end):                       # 도장 직인: 사각 → 글자
        sq = "button:text-is('사각')"
        x, y, b = self.center(sq, s.label)
        s0 = self.now()
        self.sleep(0.4)
        self.glide(x, y, 0.8)
        self.sleep(0.25)
        self.click()
        self.sleep(0.4)
        tx, ty, tb = self.center("textarea >> nth=0", s.label)
        self.glide(tx - 30, ty - 20, 0.5)
        self.typ("textarea >> nth=0", "태권월드", 0.12)
        self.wait_until(end - 0.2)
        self.spot(self.rect(b["x"], b["y"] - 35, 650, 180), s0, self.now() + 1.2, 8)

    def do_A1(self, s, end):                       # 주소 검색 창
        pg = self.pg
        x, y, b = self.center("input[name=road_address]", s.label)
        s0 = self.now()
        self.glide(x - 120, y, 0.8)
        self.sleep(0.2)
        fr = None
        tries = 3 if self.mode == "dry" else 1        # 녹화 중 실패하면 그 녹화만 다시 찍는다(영상에 재시도가 남지 않게)
        for t in range(tries):
            self.click()
            if t == 0 and self.mode == "dry":
                self.sleep(2.5)
                pg.screenshot(path=str(self.out_dir / "a1_click.png"))
                self.say("[디버그] daum: " + str(pg.evaluate("() => [Object.keys(window.daum||{}), typeof (window.daum&&daum.Postcode), performance.getEntriesByType('resource').map(e=>e.name).filter(n=>/daum|kakao/.test(n)).map(n=>n.slice(0,90))]")))
                self.say("[디버그] modal: " + str(pg.evaluate("() => { const m=document.querySelector('.MuiModal-root'); return m ? m.innerHTML.replace(/<svg.*?<\\/svg>/g,'').slice(0,600) : 'no modal'; }")))
            for _ in range(48):
                self.sleep(0.25)
                fr = next((f for f in pg.frames if "postcode" in f.url and f.locator("#region_name").count()), None)
                if fr:
                    break
            if fr:
                break
            pg.keyboard.press("Escape")
            pg.mouse.click(60, 1000)
            self.sleep(1.0)
            self.say(f"[녹화] 주소 검색 창이 안 열려서 다시 눌러요 ({t + 1})")
        if not fr:
            self.say("[디버그] frames: " + " | ".join(f.url[:80] for f in pg.frames))
            self.say("[디버그] daum: " + str(pg.evaluate("() => [typeof window.daum, [...document.scripts].map(s=>s.src).filter(x=>x.includes('postcode')||x.includes('daum')), document.querySelectorAll('.MuiModal-root iframe, .MuiModal-root *').length]")))
            self.say("[디버그] console: " + " | ".join(getattr(self, '_con', [])[-6:]))
            self.say("[디버그] blocked: " + " | ".join(self.log.get("blocked", [])[-8:]))
            raise SceneError(s, "주소 검색 창", "주소 검색 창이 열리지 않았어요")
        self.spot(b, s0, self.now(), 8)
        s1 = self.now()
        self.iframe_cursor = True
        ib = fr.locator("#region_name").bounding_box()
        self.glide(ib["x"] + 60, ib["y"] + ib["height"] / 2, 0.6)
        self.log["clicks"].append({"t": round(self.now(), 3), "x": self.pos[0] * 1.5, "y": self.pos[1] * 1.5})
        fr.locator("#region_name").focus()
        for ch in "국회대로72길 22":
            pg.keyboard.type(ch)
            self.sleep(0.09)
        self.sleep(0.3)
        pg.keyboard.press("Enter")
        res = fr.locator("button.link_post").filter(has_text="국회대로72길 22").first
        res.wait_for(timeout=15000)
        self.sleep(0.6)
        rb = res.bounding_box()
        self.glide(rb["x"] + 60, rb["y"] + rb["height"] / 2, 0.7)
        self.sleep(0.3)
        self.click()
        try:
            pg.locator(".MuiModal-root").wait_for(state="detached", timeout=4000)
        except Exception:
            res.click(timeout=3000)                 # 좌표 클릭이 안 먹으면 같은 자리를 요소로 한 번 더
            try:
                pg.locator(".MuiModal-root").wait_for(state="detached", timeout=5000)
            except Exception:
                raise SceneError(s, "주소 검색 창", "주소를 골랐는데 창이 닫히지 않았어요")
        self.iframe_cursor = False
        fb = fr_box = self.rect(610, 280, 700, 520)      # 주소 검색 창 자리(화면 가운데)
        self.spot(fr_box, s1, self.now(), 0)
        if self.mode == "dry" and not pg.locator("input[name=road_address]").input_value():
            raise SceneError(s, "도장 주소", "고른 주소가 칸에 들어가지 않았어요")

    def do_G1(self, s, end):                       # 등록(저장 차단) → 도장 목록
        btn = "button:text-is('등록')"
        s0, b = self.approach(btn, end, frac=0.45)
        self.wait_until(end - 0.35)
        self.click()
        self.spot(b, s0, self.now() + 0.4, 8)
        self.sleep(0.8)
        self.pg.goto(SELECT_URL, wait_until="domcontentloaded", timeout=30000)
        self.pg.locator(".__tm_keep button:has-text('관리하러 가기')").wait_for(timeout=20000)
        self.sleep(0.3)

    def dialog_box(self):
        return self.pg.evaluate("""() => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').includes('태권월드가 처음이신가요'));
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>380 && r.height>500) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""")

    def do_H2(self, s, end):                       # 안내 창 전체
        b = self.dialog_box() or self.rect(742, 200, 436, 680)
        s0 = self.now()
        self.glide(b["x"] + b["width"] + 40, b["y"] + 80, 0.9)
        self.spot(b, s0, end, 6)

    def do_H3(self, s, end):                       # 시작 순서 6개를 위에서 아래로
        pill = """(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<5&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>240) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; }
            const r=t.getBoundingClientRect(); return {x:r.x-100,y:r.y-12,width:r.width+200,height:r.height+24}; }"""
        top = self.pg.evaluate(pill, "반 만들기")
        bot = self.pg.evaluate(pill, "차량 등록")
        u = self.rect(top["x"], top["y"], top["width"], bot["y"] + bot["height"] - top["y"])
        s0 = self.now()
        x = top["x"] + top["width"] + 30
        self.glide(x, top["y"] + top["height"] / 2, 0.5)
        self.glide(x, bot["y"] + bot["height"] / 2, max(1.0, self.dur[s.key] - 1.2))
        self.spot(u, s0, end, 10)

    def menu_box(self, word):
        return self.pg.evaluate("""(w) => { for (const e of document.querySelectorAll('*')) {
            if (e.childElementCount===0 && (e.innerText||'').trim()===w) { const r=e.getBoundingClientRect(); if (r.x < 240 && r.width>0) {
              let c=e; for(let i=0;i<4&&c;i++){ const q=c.getBoundingClientRect(); if (q.width>180) return {x:q.x,y:q.y,width:q.width,height:q.height}; c=c.parentElement; }
              return {x:r.x,y:r.y,width:r.width,height:r.height}; } } } return null; }""", word)

    def do_H5(self, s, end):                       # 왼쪽 메뉴: 수련생 → 출결 → 납부
        boxes = [self.menu_box(w) for w in ("수련생", "출결", "납부")]
        if not all(boxes):
            raise SceneError(s, "왼쪽 메뉴", "왼쪽 메뉴를 찾지 못했어요")
        u = self.rect(boxes[0]["x"], boxes[0]["y"], boxes[0]["width"], boxes[-1]["y"] + boxes[-1]["height"] - boxes[0]["y"])
        s0 = self.now()
        seg = max(0.5, (self.dur[s.key] - 0.6) / 3)
        for b in boxes:
            self.glide(b["x"] + 110, b["y"] + b["height"] / 2, min(0.7, seg * 0.6))
            self.sleep(seg * 0.4)
        self.spot(u, s0, end, 8)


maker.Recorder = Ep2Recorder


def load():
    txt = (HERE / "scenario.yaml").read_text(encoding="utf-8").replace("{ID}", os.environ["TW_DEMO_ID"])
    import tempfile                       # 아이디가 들어간 사본은 저장소 밖(임시 폴더)에만 둔다
    tmp = Path(tempfile.gettempdir()) / f"tw_{HERE.name}_scenario.yaml"
    tmp.write_text(txt, encoding="utf-8")
    return S.load(tmp)


if __name__ == "__main__":
    mode = sys.argv[1]
    work = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "output" / "taekwonworld" / HERE.name
    work.mkdir(parents=True, exist_ok=True)
    sc = load()
    if "--silent" in sys.argv:
        from autoedit.tutorial import voices as V
        sc.brand.voice = V.SILENT                 # 현수 목소리 파일이 오기 전: 자막만으로 먼저 완성
    if mode == "check":
        dur = maker.narrate(sc, work)
        print(maker.rehearse(sc, work, dur))
    else:
        res = maker.make(sc, work, fast="--fast" in sys.argv)
        print(res)

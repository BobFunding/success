"""4편(급띠 체계 맞추기) 만들기: 3편 녹화기(로그인·도장 선택·안내 창·저장 차단) + 이 편만의 동작.
사용: . ./.env.sh && python run_ep4.py check|make [작업폴더] [--fast] [--silent]
- 초록띠 아래 [+] → '초파띠' 2선, 색1 초록·색2 파랑 → 급수가 겹치지 않게 위쪽 급수를 하나씩 올림 → 저장하기(차단).
- 저장 요청은 막혀서 실제 급띠 체계는 바뀌지 않는다.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.resolve().parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep3 as E3                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

AFTER = "초록띠"            # 이 띠 아래에 새 띠를 넣는다
NEW = "초파띠"
GREEN, BLUE = "#00CC00", "#1F00B2"


class Ep4Recorder(E3.Ep3Recorder):
    def run_scene(self, s, last):
        if s.key == "P1":
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super(E3.Ep3Recorder, self).run_scene(s, last)

    def guide_box(self, title):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>400 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""", title)

    def do_P1(self, s, end):                       # 안내 창 → 급띠 체계 맞추기
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("급띠 체계 맞추기")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/manage/levelsystem", timeout=20000)
        self.pg.get_by_text("급/띠 체계 사용 가이드").wait_for(timeout=20000)
        self.sleep(0.3)

    def do_P2(self, s, end):                       # 사용 가이드 → 닫기
        close = self.pg.get_by_text("닫기", exact=True).last
        b = close.bounding_box()
        guide = self.guide_box("급/띠 체계 사용 가이드")
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.get_by_text("급/띠 체계 사용 가이드").wait_for(state="hidden", timeout=8000)

    def do_P3(self, s, end):                       # 급띠 목록 표
        t = self.pg.evaluate("""() => { const h=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()==='띠이름');
            let c=h; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.height>400) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""")
        if not t:
            raise SceneError(s, "급띠 목록", "급띠 표를 찾지 못했어요")
        s0 = self.now()
        self.glide(t["x"] + t["width"] * 0.62, t["y"] + 60, 0.7)
        self.glide(t["x"] + t["width"] * 0.62, t["y"] + min(t["height"], 900) - 60, max(1.0, self.dur[s.key] - 1.0))
        self.spot(t, s0, end, 4)

    def do_P4(self, s, end):                       # 왼쪽 메뉴: 도장 관리 → 급띠체계
        top, it = self.side("도장 관리"), self.side("급띠체계")
        if not (top and it):
            raise SceneError(s, "왼쪽 메뉴", "도장 관리·급띠체계 메뉴를 찾지 못했어요")
        s0 = self.now()
        seg = max(0.6, (self.dur[s.key] - 0.6) / 2)
        self.glide(top["x"] + 120, top["y"] + top["height"] / 2, min(0.8, seg * 0.6))
        self.spot(top, s0, s0 + seg, 6)
        self.sleep(seg * 0.4)
        self.glide(it["x"] + 90, it["y"] + it["height"] / 2, min(0.8, seg * 0.6))
        self.spot(it, s0 + seg, end, 6)

    # ── 수정 화면 ──
    def idx(self, name):
        names = self.pg.eval_on_selector_all("input[name$='belt_name']", "els=>els.map(e=>e.value)")
        if name not in names:
            raise SceneError(self.scene, name, f"'{name}' 줄을 찾지 못했어요")
        return names.index(name)

    def row(self, i):
        pg = self.pg
        return pg.locator("div").filter(has=pg.locator(f"input[name='levelList.{i}.belt_name']")).filter(has=pg.locator("button")).last

    def row_box(self, i):
        a = self.box(f"input[name='levelList.{i}.level_name']", "급수")
        z = self.row(i).locator("button").last.bounding_box()
        return self.rect(a["x"] - 14, a["y"] - 8, z["x"] + z["width"] - a["x"] + 28, a["height"] + 16)

    def go_click(self, b, move=0.6):
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, move)
        self.sleep(0.12)
        self.click()

    def do_E1(self, s, end):                       # 공식 급띠체계로 변경(누르지 않음)
        x, y, b = self.center("button:has-text('공식 급띠체계로 변경')", s.label)
        s0 = self.now()
        self.glide(x + b["width"] / 2 + 30, y, 0.8)
        self.spot(b, s0, end, 8)

    def do_E2(self, s, end):                       # 초록띠 줄의 [+]
        i = self.idx(AFTER)
        rb = self.row_box(i)
        plus = self.row(i).locator("button").first.bounding_box()
        s0 = self.now()
        self.spot(rb, s0, end + 0.3, 2)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(plus["x"] + plus["width"] / 2, plus["y"] + plus["height"] / 2, 0.8)
        self.wait_until(end - 0.35)
        self.click()
        self.pg.locator(f"input[name='levelList.{i + 1}.belt_name']").wait_for(timeout=5000)
        self.sleep(0.2)
        if self.pg.locator(f"input[name='levelList.{i + 1}.belt_name']").input_value():
            raise SceneError(s, "더하기", "새 줄이 생기지 않았어요")
        self.new = i + 1

    def do_E3(self, s, end):                       # 이름 '초파띠' + 띠유형 2선
        n = self.new
        s0 = self.now()
        self.spot(self.row_box(n), s0, end + 0.2, 2)
        name = f"input[name='levelList.{n}.belt_name']"
        x, y, b = self.center(name, "띠 이름")
        self.glide(x - 30, y, 0.6)
        self.typ(name, NEW, 0.14)
        self.sleep(0.3)
        sel = self.row(n).locator(".MuiSelect-select").bounding_box()
        self.go_click(sel, 0.6)
        self.sleep(0.4)
        opt = self.pg.locator("li[role=option]:text-is('2선')").bounding_box()
        self.go_click(opt, 0.45)
        self.sleep(0.3)

    def do_E4(self, s, end):                       # 색1 초록, 색2 파랑 → 미리보기
        n = self.new
        r = self.row(n)
        s0 = self.now()
        rb = self.row_box(n)
        for k, color in ((0, GREEN), (1, BLUE)):
            sw = r.locator("div.w-\\[58px\\]").nth(k).bounding_box()
            self.go_click(sw, 0.4)
            self.sleep(0.25)
            pal = self.pg.locator(f"div[title='{color}']").first.bounding_box()
            self.spot(self.rect(sw["x"] - 10, sw["y"] - 8, 260, pal["y"] + 60 - sw["y"]), self.now() - 0.3, self.now() + 0.8, 0)
            self.go_click(pal, 0.35)
            self.sleep(0.2)
        # 미리보기 칸
        prev = self.pg.evaluate("""(y) => { let best=null; for (const e of document.querySelectorAll('div')) { const r=e.getBoundingClientRect();
            if (Math.abs(r.y + r.height/2 - y) < 12 && r.width > 30 && r.width < 70 && r.height > 18 && r.height < 40 && r.x > 1500) best={x:r.x,y:r.y,width:r.width,height:r.height}; } return best; }""",
                                rb["y"] + rb["height"] / 2)
        if prev:
            t0 = self.now()
            self.glide(prev["x"] + prev["width"] + 40, prev["y"] + prev["height"] / 2, 0.5)
            hold = max(end + 0.2, self.now() + 1.6)      # 미리보기는 꼭 1.6초 넘게 밝게
            self.spot(self.rect(prev["x"] - 12, prev["y"] - 10, prev["width"] + 24, prev["height"] + 20), t0, hold, 0)
            self.wait_until(hold - 0.2)
        if self.mode == "dry" and not prev:
            raise SceneError(s, "미리보기", "미리보기 칸을 찾지 못했어요")

    def retype(self, sel, text):
        x, y, b = self.center(sel, "급수")
        self.glide(x, y, 0.28)
        self.click()
        self.pg.keyboard.press("Control+A")
        for ch in text:
            self.pg.keyboard.type(ch)
            self.sleep(0.06)
        self.sleep(0.05)

    def do_E5(self, s, end):                       # 새 줄 급수 + 위쪽 급수 하나씩 올리기
        n = self.new
        top = self.box("input[name='levelList.0.level_name']", "급수")
        bot = self.box(f"input[name='levelList.{n}.level_name']", "급수")
        u = self.rect(top["x"] - 12, top["y"] - 8, top["width"] + 24, bot["y"] + bot["height"] - top["y"] + 16)
        s0 = self.now()
        below = int(self.pg.locator(f"input[name='levelList.{n + 1}.level_name']").input_value() or 0)
        self.retype(f"input[name='levelList.{n}.level_name']", str(below + 1))
        for i in range(n - 1, -1, -1):              # 아래에서 위로: 7, 8, 9 …
            self.retype(f"input[name='levelList.{i}.level_name']", str(below + 1 + (n - i)))
        self.spot(u, s0, max(end, self.now() + 0.6), 0)
        if self.mode == "dry":
            lv = self.pg.eval_on_selector_all("input[name$='level_name']", "els=>els.map(e=>e.value)")
            if len(set(lv)) != len(lv):
                raise SceneError(s, "급수", f"급수가 겹쳐요 {lv}")

    def do_S1(self, s, end):                       # 저장하기(차단)
        btn = "button:has-text('저장하기')"
        s0, b = self.approach(btn, end, frac=0.4)
        self.wait_until(end - 0.35)
        self.click()
        self.spot(b, s0, self.now() + 0.5, 8)
        self.sleep(0.8)
        if self.mode == "dry" and not any("taekwonworld" in x and "collect" not in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "저장하기", "저장 요청이 막히지 않았어요(또는 저장이 시작되지 않았어요)")


maker.Recorder = Ep4Recorder


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
        sc.brand.voice = V.SILENT
    if mode == "check":
        dur = {k: v[2] for k, v in maker.narrate(sc, work).items()}
        print(maker.rehearse(sc, work, dur))
    else:
        print(maker.make(sc, work, fast="--fast" in sys.argv))

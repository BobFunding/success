"""3편(반 만들기) 만들기: 튜토리얼 메이커 엔진 + 2편 녹화기(흐림·요청 차단·대기) + 이 편만의 동작.
사용: . ./.env.sh && python run_ep3.py check|make [작업폴더] [--fast] [--silent]
- 시작: 로그인·도장 선택은 미리 해 두고(영상 밖), 첫 화면 안내 창에서 시작한다.
- 저장: 반 화면에서는 반 만들기(classcreate 등 쓰기) 요청만 막는다. 반 목록 읽기(classread…)는 통과.
  막힌 저장 뒤에는 창을 닫고, 같은 이름·같은 요일로 이미 있는 'A반 오후 2시'를 결과로 보여 준다(실제로 반이 생기지 않음).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.resolve().parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep2"))
import run_ep2 as E2                                          # noqa: E402  (엔진 경로·흐림·대기 등)
from run_ep2 import maker, S, SceneError                      # noqa: E402

NAME_IN = "input[placeholder='반 이름을 입력해주세요.']"
DAYS = ("mon", "wed", "fri")                                  # 월·수·금 (목록의 A반 오후 2시와 같게)


class Ep3Recorder(E2.Ep2Recorder):
    def block_requests(self) -> None:
        if not self.sc.block_list or self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            api = "taekwonworld" in q.url
            reading = "read" in q.url.lower()
            if self.blocked(pg.url or "") and write and api and not reading:
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
            else:
                r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def run_pre(self) -> None:
        """로그인(장면 표의 미리하기) 뒤, 도장 목록에서 '태권월드 태권도장'을 골라 첫 화면으로(영상 밖)."""
        pg = self.pg
        ps = self.sc.pre_scenes[0]
        self.scene = ps
        pg.goto(self.sc.login_url, wait_until="networkidle", timeout=60000)
        for f in ps.fields:
            self.locate(f.target).fill(self.resolve_value(f), timeout=10000)
        self.locate(ps.button).click(timeout=10000)
        try:
            pg.wait_for_url(lambda u: "/account/login" not in u, timeout=30000)
        except Exception:
            raise SceneError(ps, "로그인", "로그인에 실패했어요. 보관함의 비밀번호를 확인해 주세요") from None
        pg.goto(E2.SELECT_URL, wait_until="domcontentloaded", timeout=30000)
        card = pg.locator("div[slide]").filter(has=pg.locator("p", has_text="태권월드 태권도장")).first
        card.get_by_text("관리하러 가기").click(timeout=20000)
        pg.wait_for_url("**/home", timeout=30000)
        self.scene = None

    def run_scene(self, s, last):
        if s.key == "P1":                          # 안내 창이 다 뜬 다음에 문장 시작
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super().run_scene(s, last)

    def pill(self, word):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<5&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>240) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; }
            const r=t.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", word)

    def do_P1(self, s, end):                       # 안내 창 → 반 만들기
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("반 만들기")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/manage/class/list", timeout=20000)
        self.pg.get_by_text("반 사용 가이드").wait_for(timeout=20000)
        self.sleep(0.3)

    def do_P2(self, s, end):                       # 반 사용 가이드 → 닫기
        close = self.pg.get_by_text("닫기", exact=True).last
        b = close.bounding_box()
        guide = self.pg.evaluate("""() => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()==='반 사용 가이드');
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>400 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""")
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.get_by_text("반 사용 가이드").wait_for(state="hidden", timeout=8000)

    def side(self, word):
        """왼쪽 메뉴에서 글자가 꼭 같은 줄(가장 작은 상자). 하위 메뉴(li)는 물결 효과 span 이 있어 맨 끝 요소가 아니다."""
        return self.pg.evaluate("""(w) => { let best=null;
            for (const e of document.querySelectorAll('li, p, a, div, span')) {
              if ((e.innerText||'').trim() !== w) continue;
              const r=e.getBoundingClientRect(); if (r.x > 240 || r.height <= 0) continue;
              if (!best || r.width*r.height < best.width*best.height) best={x:r.x,y:r.y,width:r.width,height:r.height}; }
            if (best && best.width < 180) { best.x = 0; best.width = 232; }
            return best; }""", word)

    def do_P3(self, s, end):                       # 왼쪽 메뉴: 도장 관리 → 반
        top, cls = self.side("도장 관리"), self.side("반")
        if not (top and cls):
            raise SceneError(s, "왼쪽 메뉴", "도장 관리·반 메뉴를 찾지 못했어요")
        s0 = self.now()
        seg = max(0.6, (self.dur[s.key] - 0.6) / 2)
        self.glide(top["x"] + 120, top["y"] + top["height"] / 2, min(0.8, seg * 0.6))
        self.spot(top, s0, s0 + seg, 6)
        self.sleep(seg * 0.4)
        self.glide(cls["x"] + 80, cls["y"] + cls["height"] / 2, min(0.8, seg * 0.6))
        self.spot(cls, s0 + seg, end, 6)

    def pick_time(self, idx, text):
        """idx 번째 시간 칸(0 부터: 월 시작, 월 종료, 수 시작…)을 눌러 목록에서 text 를 고른다."""
        sel = f"input[type=text] >> nth={idx + 1}"
        x, y, b = self.center(sel, "시간")
        t0 = self.now()
        self.glide(x, y, 0.45)
        self.sleep(0.12)
        self.click()
        self.sleep(0.3)
        li = self.pg.locator(f"li.react-datepicker__time-list-item:text-is('{text}')").first
        li.scroll_into_view_if_needed(timeout=5000)
        lst = self.pg.locator(".react-datepicker__time-container, .react-datepicker").first.bounding_box()
        self.sleep(0.25)
        lb = li.bounding_box()
        # 칸과 펼쳐진 시간 목록을 함께 밝게(목록에서 고르는 모습이 보이게)
        u = b if not lst else self.rect(min(b["x"], lst["x"]) - 6, b["y"] - 6,
                                        max(b["x"] + b["width"], lst["x"] + lst["width"]) - min(b["x"], lst["x"]) + 12,
                                        lst["y"] + lst["height"] - b["y"] + 12)
        self.glide(lb["x"] + lb["width"] / 2, lb["y"] + lb["height"] / 2, 0.4)
        self.sleep(0.1)
        self.click()
        self.spot(u, t0, self.now() + 0.15, 0)
        self.sleep(0.2)
        return b

    def table_box(self):
        a = self.box("input[name=mon_time]", "수업 요일")
        z = self.box("input[name=sun_time]", "수업 요일")
        return self.rect(a["x"] - 30, a["y"] - 12, z["x"] + 60 - a["x"], 100)

    def do_F2(self, s, end):                       # 월·수·금 체크
        s0 = self.now()
        self.spot(self.table_box(), s0, end, 6)
        seg = max(0.5, (self.dur[s.key] - 0.4) / len(DAYS))
        for d in DAYS:
            x, y, b = self.center(f"input[name={d}_time]", "요일")
            self.glide(x, y, min(0.55, seg * 0.6))
            self.sleep(0.1)
            self.click()
            self.sleep(max(0.1, seg * 0.3))

    def do_F3(self, s, end):                       # 월요일 2:00 PM ~ 3:00 PM
        s0 = self.now()
        a = self.pick_time(0, "2:00 PM")
        z = self.pick_time(1, "3:00 PM")
        self.spot(self.rect(a["x"] - 8, a["y"] - 8, a["width"] + 16, z["y"] + z["height"] - a["y"] + 16), self.now(), max(end, self.now() + 0.6), 4)

    def do_F4(self, s, end):                       # 수·금도 같은 시간
        s0 = self.now()
        first = None
        for i in (2, 3, 4, 5):
            b = self.pick_time(i, "2:00 PM" if i % 2 == 0 else "3:00 PM")
            first = first or b
        last = b
        self.spot(self.rect(first["x"] - 8, first["y"] - 8, last["x"] + last["width"] - first["x"] + 16, last["y"] + last["height"] - first["y"] + 16), self.now(), max(end, self.now() + 0.6), 4)
        if self.mode == "dry":
            vals = self.pg.eval_on_selector_all("input[type=text]", "els=>els.map(e=>e.value)")
            if vals[1:7] != ["2:00 PM", "3:00 PM"] * 3:
                raise SceneError(s, "시간", f"시간이 다 들어가지 않았어요 {vals}")

    def do_S1(self, s, end):                       # 저장(차단) → 창 닫기
        btn = "button:text-is('저장')"
        s0, b = self.approach(btn, end, frac=0.4)
        self.wait_until(end - 0.35)
        self.click()
        self.spot(b, s0, self.now() + 0.4, 8)
        self.sleep(0.6)
        back = self.pg.locator("button:has(+ div:text-is('반 만들기'))").first
        bb = back.bounding_box()
        self.glide(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, 0.5)
        self.sleep(0.1)
        self.click()
        self.pg.locator(NAME_IN).wait_for(state="hidden", timeout=8000)

    def do_S2(self, s, end):                       # 목록의 A반 오후 2시
        row = self.pg.locator("div.flex.h-\\[60px\\]", has_text="A반 오후 2시").first
        b = row.bounding_box()
        if not b:
            raise SceneError(s, "반 목록", "반 목록에서 'A반 오후 2시'를 찾지 못했어요")
        s0 = self.now()
        self.glide(b["x"] + 700, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"], b["y"], b["width"], b["height"]), s0, end, 6)


maker.Recorder = Ep3Recorder


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

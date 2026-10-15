"""16편(체력평가) 만들기: 15편 녹화기(가이드 닫기·글자 찾기) + 이 편만의 동작.
사용: python run_ep16.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 공식 사용자 가이드에 아직 체력평가가 없어 메뉴 순서(측정종목 관리 → 측정기록 등록 → 조회)로 찍는다. 화면에 사용 가이드 창도 없다.
- 안전: 체력평가 화면의 쓰기 요청(기록 저장·종목 저장)은 모두 막는다. 종목 선택 창은 저장하지 않고 닫는다.
- 조회·평가서는 데모 도장에 실제로 있는 2026년 9월 22일 기록(읽기만).
- 흐림: 수련생 이름, 생년월일(목록·추가 창·평가서).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep15"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep15 as E15                                        # noqa: E402
from run_ep15 import maker, S, SceneError, E12, SCALE         # noqa: E402

E12.PHONE = (HERE / "phone" / "phone.html").as_uri()          # 12편 phone() 이 이 편 휴대폰 화면을 연다
KID = "조수린"                                                # 기록 적기에서 추가하는 수련생(이름은 흐림)
REC = {"왕복오래달리기": "32", "50m달리기": "9.8"}             # 예시 기록(저장되지 않음)

# 체력평가 화면: 사진 옆 이름, 생년월일(1989-12-28, 1989-12-28 (37살))
BLUR16 = r"""(() => {
  const skip = /남자|여자|조회|선택|전체|수련생|성별|나이|생년월일|추가|삭제|저장|변경|등급|백분율|종목|체력|평가|반$|띠$|급$|품$|단$|살$|세$/;
  const run = () => {
    if (!/\/fitness/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (/^\d{4}-\d{2}-\d{2}( \(\d+살\))?$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t) || e.closest('button')) continue;   // 종목 버튼(악력 등)은 이름이 아님
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, i = 0; p && i < 4; p = p.parentElement, i++)
        if (p.querySelector('img, input[type=checkbox]')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 80);
})()"""


class Ep16Recorder(E15.Ep15Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR16)
        super().scenario()

    def side(self, word):
        """왼쪽 메뉴 줄(체력평가 하위 메뉴에는 'new' 표시가 붙어 있어 그 글자는 빼고 비교)."""
        return self.pg.evaluate("""(w) => { let best=null;
            for (const e of document.querySelectorAll('li, p, a, div, span')) {
              if ((e.innerText||'').replace(/new/g, '').trim() !== w) continue;
              const r=e.getBoundingClientRect(); if (r.x > 240 || r.height <= 0) continue;
              if (!best || r.width*r.height < best.width*best.height) best={x:r.x,y:r.y,width:r.width,height:r.height}; }
            if (best && best.width < 180) { best.x = 0; best.width = 232; }
            return best; }""", word)

    def outside_close(self):                       # 창 바깥(왼쪽 아래 빈 곳)을 눌러 닫기
        self.glide(130, 940, 0.5)
        self.sleep(0.05)
        self.click()
        self.nozoom()
        self.sleep(0.6)

    # ── 1단계: 측정종목 고르기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "체력평가", "측정종목 관리", "/fitness/management")
        self.pg.get_by_text("사용할 종목 선택").first.wait_for(timeout=15000)

    def do_S1(self, s, end):                       # PAPS 안내 → 다섯 가지 체력
        pg = self.pg
        note = self.leaf("학생건강체력평가(PAPS)") or self.holder_box("※ 체력평가", 600, 30)
        a = self.leaf("근력·근지구력")
        z = self.leaf("체질량지수")
        if note:
            self.spot(self.rect(270, note["y"] - 14, 1610, 80), self.now(), self.now() + max(1.6, self.dur[s.key] * 0.4), 0)
            self.glide(note["x"] + 100, note["y"] + note["height"] / 2, 0.8)
            self.sleep(max(0.8, self.dur[s.key] * 0.35))
        if a and z:
            self.spot(self.rect(300, a["y"] - 34, 1550, z["y"] + z["height"] + 34 - (a["y"] - 34)), self.now(), end + 0.2, 0)
            self.glide(a["x"] + 40, a["y"] + a["height"] / 2, 0.6)
            self.glide(z["x"] + 40, z["y"] + z["height"] / 2, max(0.8, self.dur[s.key] * 0.3))

    def do_S2(self, s, end):                       # 사용할 종목 선택 창(저장하지 않고 닫기)
        pg = self.pg
        b = self.box_of(pg.locator("button").filter(has_text="사용할 종목 선택").first)
        s0 = self.now()
        self.go_click(b, 0.8)
        self.spot(b, s0, self.now() + 0.2, 8)
        m = pg.locator(".MuiModal-root").filter(has_text="사용할 종목 선택").last
        m.get_by_text("50m달리기", exact=True).first.wait_for(timeout=8000)
        self.sleep(0.4)
        box = self.box_of(m.locator(".MuiPaper-root, [role=dialog]").first) if m.locator(".MuiPaper-root, [role=dialog]").count() else None
        if box:
            self.spot(box, self.now(), end - 0.5, 4)
        for w in ("팔굽혀펴기", "왕복오래달리기", "50m달리기"):
            t = self.box_of(m.get_by_text(w, exact=True).first)
            self.glide(t["x"] + t["width"] / 2, t["y"] + t["height"] / 2, 0.6)
            self.sleep(max(0.3, self.dur[s.key] * 0.08))
        self.wait_until(end - 0.5)
        self.outside_close()
        if pg.locator(".MuiModal-root").filter(has_text="사용할 종목 선택").count():
            pg.keyboard.press("Escape"); self.sleep(0.4)

    def do_S3(self, s, end):                       # 새 종목 추가(가리키기만)
        b = self.box_of(self.pg.locator("button").filter(has_text="새 종목 추가").first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(b, self.now() - 0.4, end + 0.2, 8)
        self.wait_until(end - 0.1)

    # ── 2단계: 측정기록 적기 ──
    def do_R0(self, s, end):
        self.menu_go(s, end, "체력평가", "측정기록 등록", "/fitness/regist")
        self.pg.locator("button").filter(has_text="수련생 추가").first.wait_for(timeout=15000)
        self.sleep(0.3)

    def do_R1(self, s, end):                       # 날짜·차수·변경(가리키기만)
        pg = self.pg
        chg = self.box_of(pg.locator("button").filter(has_text="변경").first)
        d = self.leaf("2026.10.15")
        box = self.rect(262, 95, chg["x"] + chg["width"] + 16 - 262, 70)
        self.spot(box, self.now(), end + 0.2, 0)
        if d:
            self.glide(d["x"] + 40, d["y"] + d["height"] / 2, 0.8)
        self.sleep(max(0.8, self.dur[s.key] * 0.45))
        self.glide(chg["x"] + chg["width"] / 2, chg["y"] + chg["height"] / 2, 0.7)

    def do_R2(self, s, end):                       # 수련생 추가 → 체크 → 추가
        pg = self.pg
        b = self.box_of(pg.locator("button").filter(has_text="수련생 추가").first)
        s0 = self.now()
        self.go_click(b, 0.8)
        self.spot(b, s0, self.now() + 0.2, 8)
        m = pg.locator(".MuiModal-root").last
        m.get_by_text(KID, exact=True).first.wait_for(timeout=8000)
        self.sleep(0.5)
        nb = self.box_of(m.get_by_text(KID, exact=True).first)
        cb = {"x": 573, "y": nb["y"] + nb["height"] / 2 - 8, "width": 16, "height": 16}
        add = self.box_of(m.locator("button").filter(has_text="추가").first)
        self.spot(self.rect(546, nb["y"] - 22, 828, nb["height"] + 44), self.now(), self.now() + 2.2, 0)
        self.go_click(cb, 0.8)
        self.sleep(max(0.5, self.dur[s.key] * 0.2))
        s1 = self.now()
        self.go_click(add, 0.7)
        self.spot(add, s1 - 0.3, self.now() + 0.2, 8)
        pg.locator("input[name^='data.0.records']").first.wait_for(timeout=8000)
        self.sleep(0.4)

    def do_R3(self, s, end):                       # 종목 탭 → 기록 적기(두 종목)
        pg = self.pg
        for i, (ev, val) in enumerate(REC.items()):
            if i:
                t = self.box_of(pg.get_by_text(ev, exact=True).first)
                self.go_click(t, 0.7)
                self.sleep(0.4)
            ib = self.box_of(pg.locator("input[name^='data.0.records']").first)
            tab = self.box_of(pg.get_by_text(ev, exact=True).first)
            self.spot(self.union(tab, ib, pad=8), self.now(), self.now() + max(1.4, self.dur[s.key] * 0.45), 0)
            self.glide(ib["x"] + 60, ib["y"] + ib["height"] / 2, 0.6)
            self.click()
            self.sleep(0.15)
            pg.keyboard.type(val, delay=110)
            self.sleep(0.4)

    def do_R4(self, s, end):                       # 저장(막힘)
        pg = self.pg
        b = self.box_of(pg.locator("button").filter(has_text="저장").last)
        s0 = self.now()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(b, s0 + 0.2, end + 0.2, 10)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.8)
        if self.mode == "dry" and not any("taekwonworld.pe.kr" in x and "fitness" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "저장", "저장 단추가 눌리지 않았어요")
        for _ in range(2):                         # 막힘 안내 창이 뜨면 닫는다
            if pg.locator(".MuiModal-root").count():
                pg.keyboard.press("Escape"); self.sleep(0.4)

    # ── 3단계: 결과 보기 ──
    def do_Q1(self, s, end):
        self.menu_go(s, end, "체력평가", "조회", "/fitness/list")
        self.sleep(0.4)

    def do_Q2(self, s, end):                       # 10월 → 9월(키보드, 고르면 바로 조회) → 결과 표
        pg = self.pg
        sel = pg.locator(".MuiSelect-select").filter(has_text="10월").first
        b = self.box_of(sel)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, 440, b["height"] + 16), self.now(), self.now() + 2.4, 0)
        self.go_click(b, 0.8)
        opt = pg.get_by_role("option", name="9월", exact=True).first
        opt.wait_for(timeout=5000)
        self.sleep(0.3)
        o = self.box_of(opt)
        self.glide(o["x"] + 60, o["y"] + o["height"] / 2, 0.5)
        self.log["clicks"].append({"t": round(self.now(), 3), "x": self.pos[0] * SCALE, "y": self.pos[1] * SCALE})
        pg.keyboard.press("ArrowUp"); self.sleep(0.03)
        pg.keyboard.press("Enter")
        pg.wait_for_url("**m=9**", timeout=10000)
        pg.locator("button").filter(has_text="평가서").first.wait_for(timeout=10000)
        self.sleep(0.4)
        self.spin_wait()
        head = self.leaf("근력, 근지구력") or self.leaf("심폐지구력")
        row = self.box_of(pg.locator("button").filter(has_text="평가서").first)
        top = (head["y"] - 14) if head else 155
        self.spot(self.rect(262, top, 1630, row["y"] + row["height"] + 20 - top), self.now(), end + 0.2, 0)
        g = self.leaf("종합등급")
        if g:
            self.glide(1000, row["y"] + row["height"] / 2, 0.6)
            self.sleep(max(0.6, self.dur[s.key] * 0.2))
            self.glide(g["x"] + 20, row["y"] + row["height"] / 2, 0.7)

    def do_Q3(self, s, end):                       # 평가서 → 창
        pg = self.pg
        b = self.box_of(pg.locator("button").filter(has_text="평가서").first)
        s0 = self.now()
        self.go_click(b, 0.8)
        self.spot(b, s0, self.now() + 0.2, 8)
        pg.get_by_text("종합평가 등급").first.wait_for(timeout=10000)
        self.sleep(0.8)
        g = self.holder_box("종합평가 그래프", 300, 300)
        r = self.holder_box("종합평가 등급", 300, 300)
        if g and r:
            self.spot(self.union(g, r, pad=6), self.now(), end + 0.2, 0)
            self.glide(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2, 0.7)
            self.sleep(max(0.6, self.dur[s.key] * 0.3))
            self.glide(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2, 0.7)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)
    def do_M2(self, s, end): self.phone(s, end, 2)


maker.Recorder = Ep16Recorder


def load():
    import tempfile                       # 아이디가 들어간 사본은 저장소 밖(임시 폴더)에만 둔다
    txt = (HERE / "scenario.yaml").read_text(encoding="utf-8").replace("{ID}", os.environ["TW_DEMO_ID"])
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
        nar = maker.narrate(sc, work)
        dur = {k: v[2] for k, v in nar.items()}
        from autoedit.tutorial import qa                     # 발음부터: 녹화 뒤에 문장을 고치면 다시 찍어야 하므로
        qa.pronunciation(sc, nar, work)
        print(maker.rehearse(sc, work, dur))
    else:
        print(quick.make(maker, sc, work, HERE))

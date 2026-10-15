"""15편(승급) 만들기: 12편 녹화기(안내 창 닫기·메뉴 이동·창 닫기 nozoom·휴대폰) + 이 편만의 동작.
사용: python run_ep15.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 승급 등록은 '공식 등록, 수정·취소 불가' → 확인 창의 [등록]은 가리키기만 하고 [취소]로 닫는다. 쓰기 요청도 모두 막는다.
- 승급 이력·승급증은 데모 도장에 실제로 있는 2026년 6월 기록(읽기만). 인쇄 아이콘도 가리키기만 한다.
- 흐림: 수련생 이름(목록·명단·승급증), 심사인 전화번호.
- 만들기는 quick.make(빠른 인코딩·1080p 생략·통과한 리허설 건너뛰기).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep12"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep12 as E12                                        # noqa: E402
from run_ep12 import maker, S, SceneError                     # noqa: E402
from autoedit.tutorial.recorder import SCALE                  # noqa: E402

E12.PHONE = (HERE / "phone" / "phone.html").as_uri()          # 12편 phone() 이 이 편 휴대폰 화면을 연다
KID = "조수린"                                                # 승급 등록에서 고르는 수련생(이름은 흐림)
MONTH = "6월"                                                 # 실제 승급 기록이 있는 달

# 승급 화면: 사진 옆 이름, 승급증 속 띄어 쓴 이름, 심사인 전화번호 흐림
BLUR15 = r"""(() => {
  const skip = /남자|여자|승급|조회|선택|전체|수련생|이력|삭제|성별|나이|소속|심사|명단|정보|유형|공식|띠$|급$|품$|단$|살$/;
  const run = () => {
    if (!/\/levelup/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (/^[가-힣]( [가-힣]){1,3}$/.test(t) && e.closest('.MuiModal-root')) { e.classList.add('__tm_blur'); continue; }
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t)) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, i = 0; p && i < 6; p = p.parentElement, i++)
        if (p.querySelector('img, input[type=checkbox]')) { e.classList.add('__tm_blur'); break; }
    }
    for (const i of document.querySelectorAll('input'))
      if (/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(i.value || '')) i.classList.add('__tm_blur');
  };
  setInterval(run, 100);
})()"""


class Ep15Recorder(E12.Ep12Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR15)
        super().scenario()

    def close_guide(self, s, end, title):          # 사용 가이드 → 아래쪽 닫기(nozoom)
        pg = self.pg
        guide = self.guide_box(title)
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        b = self.box_of(pg.get_by_text("닫기", exact=True).last)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.nozoom()
        self.sleep(0.6)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    def leaf(self, text, ymax=1080, xmin=240):
        return self.pg.evaluate("""([w, ymax, xmin]) => { const t=[...document.querySelectorAll('*')].find(e=>!e.childElementCount && (e.innerText||'').trim()===w
               && e.getBoundingClientRect().x>=xmin && e.getBoundingClientRect().y<ymax && e.getBoundingClientRect().width>0);
            if (!t) return null; const r=t.getBoundingClientRect(); return {x:r.x, y:r.y, width:r.width, height:r.height}; }""", [text, ymax, xmin])

    # ── 1단계: 승급 등록하기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "승급", "승급 등록", "/levelup/regist/select")
        self.pg.get_by_text("승급 등록 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):
        self.close_guide(s, end, "승급 등록 사용 가이드")

    def do_R1(self, s, end):                       # 조수린 체크 → 선택
        pg = self.pg
        row = pg.locator("div").filter(has=pg.get_by_text(KID, exact=True)).filter(has=pg.locator("input[type=checkbox]")).last
        cb = self.box_of(row.locator("input[type=checkbox]").first)
        rb = self.box_of(row)
        sel = self.box_of(pg.get_by_role("button", name="선택", exact=True).first)
        self.spot(rb, self.now(), self.now() + max(1.6, self.dur[s.key] * 0.45), 0)
        self.sleep(0.3)
        self.go_click(cb, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        s0 = self.now()
        self.go_click(sel, 0.8)
        self.spot(sel, s0 - 0.2, self.now() + 0.2, 8)
        pg.wait_for_url("**/levelup/regist?**", timeout=15000)
        pg.get_by_text("승급자 명단").first.wait_for(timeout=10000)
        self.sleep(0.6)
        self.spin_wait()

    def do_R2(self, s, end):                       # 지금 급 → 올라갈 급
        a = self.leaf("8급", 300)
        z = self.leaf("7급", 300)
        if not (a and z):
            raise SceneError(s, "승급 급수", "지금 급과 올라갈 급을 찾지 못했어요")
        band = self.rect(a["x"] - 20, a["y"] - 22, z["x"] + 140 - a["x"], a["height"] + 44)
        self.spot(band, self.now(), end + 0.2, 0)
        self.glide(a["x"] + 20, a["y"] + a["height"] / 2, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.35))
        self.glide(z["x"] + 20, z["y"] + z["height"] / 2, 0.8)

    def do_R3(self, s, end):                       # 승급일 → 승급 버튼 → 확인 창
        pg = self.pg
        d = self.leaf("승급일", 900)
        btn = self.box_of(pg.locator("button").filter(has_text="승급").last)
        if d:
            box = self.rect(d["x"] - 10, d["y"] - 22, 470, d["height"] + 44)
            self.spot(box, self.now(), self.now() + max(1.4, self.dur[s.key] * 0.4), 0)
            self.glide(d["x"] + 240, d["y"] + d["height"] / 2, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        s0 = self.now()
        self.glide(btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2, 0.8)
        self.spot(btn, s0, end + 0.2, 10)
        self.wait_until(end - 0.35)
        self.click()
        pg.get_by_text("등록 하시겠습니까?").first.wait_for(timeout=8000)
        self.sleep(0.4)

    def do_R4(self, s, end):                       # 확인 창: [등록]은 가리키기만 → [취소]
        pg = self.pg
        m = pg.locator(".MuiModal-root").filter(has_text="등록 하시겠습니까?").last
        reg = self.box_of(m.get_by_role("button", name="등록", exact=True).first)
        cancel = self.box_of(m.get_by_role("button", name="취소", exact=True).first)
        box = self.box_of(m.locator(".MuiPaper-root, [role=dialog]").first) if m.locator(".MuiPaper-root, [role=dialog]").count() else None
        if box:
            self.spot(box, self.now(), self.now() + max(1.2, self.dur[s.key] * 0.3), 4)
        self.sleep(max(0.5, self.dur[s.key] * 0.2))
        self.glide(reg["x"] + reg["width"] / 2, reg["y"] + reg["height"] / 2, 0.7)       # 가리키기만
        self.spot(reg, self.now() - 0.3, end - 0.6, 8)
        self.wait_until(end - 0.7)
        self.glide(cancel["x"] + cancel["width"] / 2, cancel["y"] + cancel["height"] / 2, 0.4)
        self.click()
        self.nozoom()
        self.sleep(0.5)
        if pg.get_by_text("등록 하시겠습니까?").count() and pg.get_by_text("등록 하시겠습니까?").first.is_visible():
            raise SceneError(s, "취소", "확인 창이 닫히지 않았어요")
        if any("taekwonworld.pe.kr" in x and "levelup" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", "승급 등록 요청이 나갔어요(막힘) — 등록을 누르면 안 돼요")

    # ── 2단계: 승급 이력 보기 ──
    def do_H1(self, s, end):
        self.menu_go(s, end, "승급", "조회", "/levelup/history")
        self.pg.get_by_text("승급 이력 사용 가이드").first.wait_for(timeout=15000)

    def do_H2(self, s, end):
        self.close_guide(s, end, "승급 이력 사용 가이드")

    def do_H3(self, s, end):                       # 10월 → 6월(고르면 바로 조회) → 목록
        pg = self.pg
        sel = pg.locator(".MuiSelect-select").filter(has_text="10월").first
        b = self.box_of(sel)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now(), self.now() + 2.4, 0)
        self.go_click(b, 0.8)
        opt = pg.get_by_role("option", name=MONTH, exact=True).first
        opt.wait_for(timeout=5000)
        self.sleep(0.4)
        o = self.box_of(opt)
        self.glide(o["x"] + 60, o["y"] + o["height"] / 2, 0.6)
        # 이 목록은 마우스 클릭으로는 안 골라져서(사이트 동작) 키보드로 고른다. 클릭 효과만 그 자리에 남긴다
        self.log["clicks"].append({"t": round(self.now(), 3), "x": self.pos[0] * SCALE, "y": self.pos[1] * SCALE})
        for _ in range(10 - int(MONTH[:-1])):
            pg.keyboard.press("ArrowUp"); self.sleep(0.03)
        pg.keyboard.press("Enter")
        pg.wait_for_url(f"**m={MONTH[:-1]}**", timeout=10000)
        pg.get_by_role("button", name="승급증").first.wait_for(timeout=10000)
        self.sleep(0.4)
        self.spin_wait()
        row = self.box_of(pg.get_by_role("button", name="승급증").first)
        self.spot(self.rect(262, row["y"] - 18, 1630, row["height"] + 36), self.now(), end + 0.2, 0)
        self.glide(700, row["y"] + row["height"] / 2, 0.7)

    def do_H4(self, s, end):                       # 이력 삭제 X(가리키기만)
        pg = self.pg
        c = self.leaf("이력 삭제")
        row = self.box_of(pg.get_by_role("button", name="승급증").first)
        x = self.rect(c["x"] - 4, row["y"] - 6, c["width"] + 8, row["height"] + 12) if c else None
        if not x:
            raise SceneError(s, "이력 삭제", "이력 삭제 칸을 찾지 못했어요")
        self.spot(self.rect(c["x"] - 14, c["y"] - 14, c["width"] + 28, row["y"] + row["height"] + 20 - c["y"]), self.now(), end + 0.2, 0)
        self.glide(x["x"] + x["width"] / 2, x["y"] + x["height"] / 2, 0.8)
        self.wait_until(end - 0.1)

    # ── 3단계: 승급증 확인하기 ──
    def do_C1(self, s, end):                       # 승급증 버튼 → 승급증 창
        pg = self.pg
        b = self.box_of(pg.get_by_role("button", name="승급증").first)
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.25))
        self.go_click(b, 0.8)
        self.spot(b, s0, self.now() + 0.2, 8)
        pg.locator(".MuiModal-root svg[data-testid=PrintIcon]").first.wait_for(timeout=10000)
        self.sleep(0.8)
        self.spin_wait()

    def do_C2(self, s, end):                       # 승급증 유형 두 가지(태권월드 승급증 눌러 보기 → 공식으로 돌아오기)
        pg = self.pg
        t = self.holder_box("승급증 유형", 160, 120)
        off = self.box_of(pg.get_by_text("공식 승급증", exact=True).first)
        tw = self.box_of(pg.get_by_text("태권월드 승급증", exact=True).first)
        if t:
            self.spot(t, self.now(), end + 0.2, 6)
        self.glide(off["x"] + off["width"] / 2, off["y"] + off["height"] / 2, 0.7)
        self.sleep(max(0.5, self.dur[s.key] * 0.2))
        self.go_click(tw, 0.6)
        self.sleep(max(1.2, self.dur[s.key] * 0.35))
        self.go_click(off, 0.6)
        self.sleep(0.4)

    def do_C3(self, s, end):                       # 인쇄 아이콘(가리키기만)
        pg = self.pg
        p = self.box_of(pg.locator(".MuiModal-root button").filter(has=pg.locator("svg[data-testid=PrintIcon]")).first)
        self.glide(p["x"] + p["width"] / 2, p["y"] + p["height"] / 2, 0.8)
        self.spot(p, self.now() - 0.4, end + 0.2, 10)
        self.wait_until(end - 0.1)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)
    def do_M2(self, s, end): self.phone(s, end, 2)


maker.Recorder = Ep15Recorder


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

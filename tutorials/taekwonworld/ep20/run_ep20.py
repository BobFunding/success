"""20편(수련생 관리) 만들기: 15·16편 녹화기(가이드 닫기·메뉴·글자 찾기) + 이 편만의 동작.
사용: python run_ep20.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 쓰기(저장하기·퇴소·휴관 등록·재입관 등록)는 모두 가리키기만 하고 창은 뒤로(←)로 닫는다. 요청도 막는다.
- 흐림: 이름(목록·상세), 생년월일, 전화번호, 보호자 이름, 이메일, 주소.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep16"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep16 as E16                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

KID = "조수린"                                                # 상세·휴관에 쓰는 수련생(이름은 흐림)
LIST_URL = "/manage/student/list"

BLUR20 = r"""(() => {
  const skip = /전화번호|이메일|이름|관계|남자|여자|조회|선택|전체|수련생|성별|나이|생년월일|보호자|연락처|출석번호|납부일|수련비|휴관|일자|등록|퇴소|저장|정보|반$|띠$|급$|품$|단$|살$/;
  const sel = ['LAST_NAME', 'FIRST_NAME', 'PHONE_NUMBER', 'REP_PHONE_NUMBER', 'REP_NAME', 'REP_PHONE_NUMBER_2', 'REP_NAME_2',
               'EMAIL', 'ROAD_ADDRESS', 'ADDRESS_DETAIL'].map(n => `input[name="${n}"]`).join(',');
  const run = () => {
    if (!/\/manage\/student/.test(location.pathname)) return;
    for (const i of document.querySelectorAll(sel)) i.classList.add('__tm_blur');
    for (const i of document.querySelectorAll('input[name="DOB"]')) {             // 생년월일 고르는 칸(연·월·일)
      const box = i.closest('.MuiInputBase-root') || i.parentElement; if (box) box.classList.add('__tm_blur'); }
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (/^\d{4}-\d{2}-\d{2}( \(\d+살\))?$/.test(t) && !e.closest('.MuiModal-root')) {
        // 목록의 생년월일만(휴관 일자 칸은 남긴다): 같은 줄에 사진이 있는 칸 중 '살' 이 붙은 것 또는 생년월일 열
        if (/살\)$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      }
      if (/^0\d{1,2}-\d{3,4}-\d{4}$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t) || e.closest('button')) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, k = 0; p && k < 4; p = p.parentElement, k++)
        if (p.querySelector('img')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 80);
})()"""


class Ep20Recorder(E16.Ep16Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR20)
        super().scenario()

    def back(self, modal=None):
        """제목 옆 뒤로(←, 첫 IconButton)로 닫기/돌아가기."""
        pg = self.pg
        if modal:
            b = pg.locator(".MuiModal-root").last.locator("button.MuiIconButton-root").first.bounding_box(timeout=5000)
        else:                                      # 페이지 제목 왼쪽의 ←
            b = {"x": 262, "y": 30, "width": 22, "height": 22}           # 화면 맨 위 '←'(제목 왼쪽, 자리가 고정)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.4)
        self.click()
        self.nozoom()
        self.sleep(0.6)

    def kid_row(self):
        """목록에서 KID 줄: (이름 상자, 줄 상자, 그 줄 체크박스 상자). 체크박스는 이름과 같은 높이의 것."""
        pg = self.pg
        nb = self.box_of(pg.get_by_text(KID, exact=True).first)
        cy = nb["y"] + nb["height"] / 2
        cb = pg.evaluate("""(cy) => { let best=null; for (const e of document.querySelectorAll('input[type=checkbox]')) {
              const r=e.getBoundingClientRect(); if (r.width<=0 || r.x>400) continue; const d=Math.abs(r.y+r.height/2-cy);
              if (d<25 && (!best || d<best.d)) best={x:r.x,y:r.y,width:r.width,height:r.height,d,i:[...document.querySelectorAll('input[type=checkbox]')].indexOf(e)}; } return best; }""", cy)
        if not cb:
            raise SceneError(self.scene, "체크", "수련생 줄의 체크 칸을 찾지 못했어요")
        row = self.rect(262, cy - 30, 1630, 60)
        return nb, row, cb

    # ── 1단계: 정보 고치기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "수련생", "전체 조회", LIST_URL)
        self.pg.get_by_text("휴관 등록 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):
        self.close_guide(s, end, "수련생 조회 - 휴관 등록 사용 가이드")

    def do_E1(self, s, end):                       # 수련생 줄 누르기 → 상세
        pg = self.pg
        _, rb, _ = self.kid_row()
        self.spot(self.rect(rb["x"], rb["y"] - 2, rb["width"], rb["height"] + 4), self.now(), self.now() + max(1.6, self.dur[s.key] * 0.5), 0)
        self.sleep(max(0.5, self.dur[s.key] * 0.3))
        self.go_click(self.rect(rb["x"] + 700, rb["y"] + rb["height"] / 2 - 5, 10, 10), 0.8)
        pg.wait_for_url("**/manage/student/detail**", timeout=15000)
        pg.locator("input[name=CLASS_ID]").first.wait_for(state="attached", timeout=15000)
        self.sleep(0.6)
        self.spin_wait()
        pg.get_by_text("기본 정보").first.wait_for(timeout=15000)
        self.sleep(1.0)

    def do_E2(self, s, end):                       # 반·급·보호자 연락처
        pg = self.pg
        lv = self.box_of(pg.locator("input[name=STUDENT_LEVEL]").locator("xpath=..").first)
        cl = self.box_of(pg.locator("input[name=CLASS_ID]").locator("xpath=..").first)
        rp = self.box_of(pg.locator("input[name=REP_PHONE_NUMBER]").first)
        self.spot(self.union(lv, cl, pad=10), self.now(), self.now() + max(1.8, self.dur[s.key] * 0.45), 0)
        self.glide(cl["x"] + 60, cl["y"] + cl["height"] / 2, 0.8)
        self.sleep(0.3)
        self.glide(lv["x"] + 60, lv["y"] + lv["height"] / 2, 0.6)
        self.sleep(max(0.4, self.dur[s.key] * 0.15))
        self.spot(self.rect(rp["x"] - 140, rp["y"] - 12, 950, rp["height"] * 2 + 40), self.now(), end + 0.2, 0)
        self.glide(rp["x"] + 60, rp["y"] + rp["height"] / 2, 0.8)

    def do_E3(self, s, end):                       # 저장하기(가리키기만)
        b = self.box_of(self.pg.get_by_role("button", name="저장하기").first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, self.now() - 0.5, end + 0.2, 10)
        self.wait_until(end - 0.1)

    def do_E4(self, s, end):                       # 맨 아래 퇴소(가리키기만)
        pg = self.pg
        h = pg.evaluate("document.documentElement.scrollHeight")
        self.scroll_to(max(0, h - 1080), 1.0)
        self.sleep(0.3)
        t = pg.get_by_text("퇴소", exact=True).last
        b = self.box_of(t)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 14, b["y"] - 10, b["width"] + 28, b["height"] + 20), self.now() - 0.4, end + 0.2, 0)
        self.wait_until(end - 0.2)
        self.scroll_to(0, 0.5)

    # ── 2단계: 휴관 처리하기 ──
    def ensure_checked(self, cb):
        """마우스 클릭이 체크 칸에 안 먹는 경우가 있어, 안 됐으면 그 칸을 직접 체크(화면 클릭 기록은 이미 남음)."""
        cbx = self.pg.locator("input[type=checkbox]").nth(cb["i"])
        self.pg.wait_for_timeout(200)
        if not cbx.is_checked():
            cbx.check(force=True)
            self.pg.wait_for_timeout(200)
        if not cbx.is_checked():
            raise SceneError(self.scene, "체크", "수련생 체크가 되지 않았어요")

    def do_R1(self, s, end):                       # 목록으로 → 체크 → 일괄 휴관
        pg = self.pg
        self.back()
        pg.wait_for_url(f"**{LIST_URL}**", timeout=15000)
        pg.get_by_text(KID, exact=True).first.wait_for(timeout=15000)
        self.sleep(0.4)
        _, rb, cb = self.kid_row()
        self.spot(self.rect(rb["x"], rb["y"] - 2, rb["width"], rb["height"] + 4), self.now(), self.now() + 2.0, 0)
        self.go_click(cb, 0.8)
        self.ensure_checked(cb)
        self.sleep(max(0.4, self.dur[s.key] * 0.2))
        b = self.box_of(pg.get_by_role("button", name="일괄 휴관").first)
        s0 = self.now()
        self.wait_until(end - 1.0)
        self.go_click(b, 0.7)
        self.spot(b, s0, self.now() + 0.2, 8)
        pg.get_by_text("휴관 일자").first.wait_for(timeout=8000)
        self.sleep(0.4)

    def do_R2(self, s, end):                       # 휴관 일자 → 등록(가리키기만) → 닫기
        pg = self.pg
        m = pg.locator(".MuiModal-root").filter(has_text="휴관 등록").last
        box = self.box_of(m.locator(".MuiPaper-root, [role=dialog]").first) if m.locator(".MuiPaper-root, [role=dialog]").count() else None
        if box:
            self.spot(box, self.now(), end - 0.5, 4)
        d = self.box_of(m.locator("input").first)
        self.go_click(d, 0.7)
        self.sleep(0.5)
        day = pg.locator(".react-datepicker__day--016:not(.react-datepicker__day--outside-month)").first
        if day.count():
            self.go_click(self.box_of(day), 0.5)
            self.sleep(0.4)
        reg = self.box_of(m.get_by_role("button", name="등록").first)
        self.glide(reg["x"] + reg["width"] / 2, reg["y"] + reg["height"] / 2, 0.7)       # 가리키기만
        self.wait_until(end - 0.6)
        self.back(modal=True)
        if pg.locator(".MuiModal-root").filter(has_text="휴관 등록").count():
            pg.keyboard.press("Escape"); self.sleep(0.4)

    def do_R3(self, s, end):                       # 휴관 수련생 포함(조회 조건, 저장 아님)
        pg = self.pg
        lab = pg.get_by_text("휴관 수련생 포함").first
        b = self.box_of(lab)
        cb = {"x": b["x"] - 26, "y": b["y"] + b["height"] / 2 - 9, "width": 18, "height": 18}
        self.spot(self.rect(b["x"] - 36, b["y"] - 10, b["width"] + 50, b["height"] + 20), self.now(), self.now() + 2.4, 0)
        self.sleep(max(0.4, self.dur[s.key] * 0.25))
        self.go_click(cb, 0.8)
        self.sleep(1.0)
        self.spin_wait()

    # ── 3단계: 재입관하기 ──
    def do_Q1(self, s, end):
        self.menu_go(s, end, "수련생", "휴관 수련생 조회", "/manage/student/rest")
        self.pg.get_by_text("재입관 사용 가이드").first.wait_for(timeout=15000)

    def do_Q2(self, s, end):
        self.close_guide(s, end, "휴관 수련생 - 재입관 사용 가이드")

    def do_Q3(self, s, end):                       # 첫 줄 체크 → 일괄 재입관
        pg = self.pg
        cbs = pg.locator("input[type=checkbox]")
        cb = dict(self.box_of(cbs.nth(1)), i=1)
        row = self.rect(262, cb["y"] - 22, 1630, cb["height"] + 44)
        self.spot(row, self.now(), self.now() + 2.0, 0)
        self.go_click(cb, 0.8)
        self.ensure_checked(cb)
        self.sleep(max(0.4, self.dur[s.key] * 0.2))
        b = self.box_of(pg.get_by_role("button", name="일괄 재입관").first)
        s0 = self.now()
        self.wait_until(end - 1.0)
        self.go_click(b, 0.7)
        self.spot(b, s0, self.now() + 0.2, 8)
        pg.locator(".MuiModal-root").last.get_by_role("button", name="등록").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_Q4(self, s, end):                       # 반 고르기(보여 주기만) → 등록 가리키기 → 닫기
        pg = self.pg
        m = pg.locator(".MuiModal-root").last
        box = self.box_of(m.locator(".MuiPaper-root, [role=dialog]").first) if m.locator(".MuiPaper-root, [role=dialog]").count() else None
        if box:
            self.spot(box, self.now(), end - 0.5, 4)
        sel = m.locator(".MuiSelect-select").first
        if sel.count():
            sb = self.box_of(sel)
            self.go_click(sb, 0.7)
            self.sleep(max(0.8, self.dur[s.key] * 0.25))
            pg.keyboard.press("Escape")
            self.sleep(0.3)
        reg = self.box_of(m.get_by_role("button", name="등록").first)
        self.glide(reg["x"] + reg["width"] / 2, reg["y"] + reg["height"] / 2, 0.7)       # 가리키기만
        self.wait_until(end - 0.6)
        self.back(modal=True)
        if pg.locator(".MuiModal-root").count():
            pg.keyboard.press("Escape"); self.sleep(0.4)


maker.Recorder = Ep20Recorder


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

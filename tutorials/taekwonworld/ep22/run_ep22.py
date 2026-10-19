"""22편(반 관리) 만들기: 21편 녹화기(메뉴·뒤로·글자 찾기) + 이 편만의 동작.
사용: python run_ep22.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 저장·담당 삭제·수련생 추가·반 삭제는 모두 가리키기만 하고 작은 창은 ←(첫 IconButton)로 닫는다. 요청도 막는다.
- 흐림: 수련생·사범님 이름(사진 옆), 나이(○살), 전화번호.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep21"))
sys.path.insert(0, str(HERE.parent / "ep20"))
sys.path.insert(0, str(HERE.parent / "ep16"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep21 as E21                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

CLS = "B반 오후 2시"                                          # 담당 사범님 1명·수련생 2명인 반
MOVE = "조현우"                                               # 수련생 추가 창에서 체크해 보이는 수련생(이름은 흐림)
LIST_URL = "/manage/class/list"

BLUR22 = r"""(() => {
  const skip = /^(남자|여자|전체 선택|반 정보|시간표|반 이름|저장|추가|삭제|조회)$/;
  const run = () => {
    if (!/\/manage\/class/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim(); if (!t) continue;
      if (/^0\d{1,2}-\d{3,4}-\d{4}$/.test(t) || /^\d{1,3}살$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      if (!/^[가-힣]{2,4}( 관장님| 사범님)?$/.test(t) || skip.test(t) || e.closest('button')) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, k = 0; p && k < 4; p = p.parentElement, k++)
        if (p.querySelector('img')) { e.classList.add('__tm_blur'); break; }
    }
    for (const im of document.querySelectorAll('img[src*="/sabum/"], img[src*="/kwanjang/"]'))   // 실제 사진이면 흐림
      im.style.setProperty('filter', 'blur(14px)', 'important');
  };
  setInterval(run, 80);
})()"""


class Ep22Recorder(E21.Ep21Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR22)
        super().scenario()

    def modal(self, title):
        return self.pg.locator(".MuiModal-root").filter(has_text=title).last

    def cb_near(self, name, modal):
        """modal 안에서 name 과 같은 높이의 체크 칸: 상자 + 전체 체크 칸 중 순번(i)."""
        nb = self.box_of(modal.get_by_text(name, exact=True).first)
        cy = nb["y"] + nb["height"] / 2
        cb = self.pg.evaluate("""(cy) => { const all=[...document.querySelectorAll('input[type=checkbox]')]; let best=null;
              for (const e of all) { const r=e.getBoundingClientRect(); if (r.width<=0) continue; const d=Math.abs(r.y+r.height/2-cy);
                if (d<25 && (!best || d<best.d)) best={x:r.x,y:r.y,width:r.width,height:r.height,d,i:all.indexOf(e)}; } return best; }""", cy)
        if not cb:
            raise SceneError(self.scene, name, "체크 칸을 찾지 못했어요")
        return nb, cb

    def close_small(self, title):                  # 작은 창: 제목 왼쪽 ←
        m = self.modal(title)
        b = self.box_of(m.locator("button.MuiIconButton-root").first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.5)
        self.click()
        self.nozoom()
        self.sleep(0.5)
        if self.modal(title).count():
            raise SceneError(self.scene, title, "창이 닫히지 않았어요")

    def press(self, s, end, name):                 # 창 여는 버튼: 가리킨 뒤 문장 끝에 누르기
        b = self.box_of(self.pg.get_by_role("button", name=name, exact=True).first)
        s0 = self.now()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.wait_until(end - 0.4)
        self.click()
        self.nozoom()                              # 누르면 큰 창이 가운데 뜨므로, 버튼 쪽으로 확대하면 창이 잘려 보인다
        self.spot(self.rect(b["x"] - 6, b["y"] - 6, b["width"] + 12, b["height"] + 12), s0, self.now() + 0.1, 6)
        self.sleep(0.6)

    def pick_and_point(self, s, end, title, name, btn):
        """작은 창: name 체크(화면 안에서만) → btn 가리키기만 → ← 로 닫기."""
        pg = self.pg
        m = self.modal(title)
        m.get_by_text(name, exact=True).first.wait_for(timeout=10000)
        self.sleep(0.4)
        nb, cb = self.cb_near(name, m)
        self.spot(self.rect(cb["x"] - 20, cb["y"] - 22, 980, cb["height"] + 44), self.now(), self.now() + max(1.6, self.dur[s.key] * 0.4), 0)
        self.go_click(cb, 0.8)
        self.ensure_checked(cb)
        self.sleep(max(0.4, self.dur[s.key] * 0.15))
        b = self.box_of(m.get_by_role("button", name=btn, exact=True).first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)                # 가리키기만
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.4, end - 0.6, 6)
        self.wait_until(end - 0.6)
        self.close_small(title)

    # ── 1단계: 반 정보 고치기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "도장 관리", "반", LIST_URL)
        self.pg.get_by_text("반 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):
        self.close_guide(s, end, "반 사용 가이드")

    def do_E1(self, s, end):
        pg = self.pg
        t = self.box_of(pg.get_by_text(CLS, exact=True).first)
        row = self.rect(262, t["y"] - 20, 1630, t["height"] + 40)
        self.spot(row, self.now(), self.now() + max(1.6, self.dur[s.key] * 0.6), 0)
        self.sleep(max(0.5, self.dur[s.key] * 0.3))
        self.go_click(self.rect(t["x"] + 20, t["y"], 40, t["height"]), 0.8)
        self.modal("반 정보").get_by_text("시간표").first.wait_for(timeout=15000)
        self.sleep(1.0)

    def do_E2(self, s, end):                       # 반 이름 → 요일 → 시간
        pg = self.pg
        m = self.modal("반 정보")
        name = self.box_of(m.locator("input[name=title]").first)
        days = self.box_of(m.get_by_text("일", exact=True).first)
        top = self.leaf("시간표")
        self.spot(self.rect(top["x"] - 14, name["y"] - 14, 1170, 240), self.now(), end + 0.2, 0)
        self.glide(name["x"] + 120, name["y"] + name["height"] / 2, 0.8)
        self.sleep(max(0.3, self.dur[s.key] * 0.2))
        tue = m.get_by_text("화", exact=True).first
        tb = self.box_of(tue)
        self.glide(tb["x"] - 20, tb["y"] + tb["height"] / 2, 0.7)
        self.sleep(max(0.3, self.dur[s.key] * 0.15))
        self.glide(tb["x"] + 10, tb["y"] + 70, 0.6)
        self.wait_until(end - 0.1)

    def do_E3(self, s, end):                       # 저장(가리키기만)
        b = self.box_of(self.modal("반 정보").get_by_role("button", name="저장", exact=True).first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.5, end + 0.2, 6)
        self.wait_until(end - 0.1)

    # ── 2단계: 소속반 바꾸기 ──
    def do_T1(self, s, end):
        self.press(s, end, "담당 삭제")
        self.modal("담당 사범님 삭제").get_by_role("button", name="삭제", exact=True).wait_for(timeout=8000)

    def do_T2(self, s, end):
        self.pick_and_point(s, end, "담당 사범님 삭제", "백관장", "삭제")

    def do_T3(self, s, end):
        self.press(s, end, "수련생 추가")
        self.modal("소속 수련생 추가").get_by_role("button", name="추가", exact=True).wait_for(timeout=8000)

    def do_T4(self, s, end):
        self.pick_and_point(s, end, "소속 수련생 추가", MOVE, "추가")

    # ── 3단계: 반 삭제하기 ──
    def do_X1(self, s, end):                       # 반 삭제(가리키기만)
        b = self.leaf("반 삭제")
        if not b:
            raise SceneError(s, "반 삭제", "버튼을 찾지 못했어요")
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 12, b["y"] - 8, b["width"] + 24, b["height"] + 16), self.now() - 0.4, end + 0.2, 4)
        self.wait_until(end - 0.1)

    def do_X2(self, s, end):                       # 담당 사범님·소속 수련생 칸
        a = self.leaf("담당 사범님 1명")
        z = self.leaf("반 삭제")
        if not a:
            raise SceneError(s, "담당 사범님", "칸을 찾지 못했어요")
        self.spot(self.rect(a["x"] - 14, a["y"] - 18, 1170, z["y"] - a["y"] - 6), self.now(), end + 0.2, 0)
        self.glide(a["x"] + 150, a["y"] + 80, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(a["x"] + 150, a["y"] + 250, 0.8)
        self.wait_until(end - 0.1)


maker.Recorder = Ep22Recorder


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

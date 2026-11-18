"""21편(사범 관리) 만들기: 20편 녹화기(메뉴·뒤로·글자 찾기) + 이 편만의 동작.
사용: python run_ep21.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 퇴사는 가리키기만 한다. 요청도 막는다(요청차단 /manage/sabum).
- 흐림: 사범님 사진(목록·상세, 글자 흐림 스타일은 그림에 안 먹어 filter 로), 이름, 생년월일, 전화번호, 이메일, 자격증 일련번호.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep20"))
sys.path.insert(0, str(HERE.parent / "ep16"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep20 as E20                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

LIST_URL = "/manage/sabum/list"

BLUR21 = r"""(() => {
  const LABELS = ['이름', '생년월일', '전화번호', '이메일', '일련번호'];
  const run = () => {
    if (!/\/manage\/sabum/.test(location.pathname)) return;
    const leaves = [...document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6, label')].filter(e => !e.childElementCount);
    for (const im of document.querySelectorAll('img')) {                       // 사범님 사진(띠 그림은 납작해서 빼고)
      const r = im.getBoundingClientRect(); if (r.x > 240 && r.height >= 30) im.style.setProperty('filter', 'blur(14px)', 'important'); }
    for (const e of leaves) {
      if (e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim(); if (!t) continue;
      if (/^0\d{1,2}-\d{3,4}-\d{4}$/.test(t) || /@/.test(t) || /^[A-Z]{2}\d{6,}$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      const r = e.getBoundingClientRect(); if (r.x < 240 || r.width <= 0) continue;
      // 목록: 사진 옆 이름
      if (/^[가-힣]{2,4}$/.test(t) && !/^(사범님|사범|담당반|입사일|휴대전화|기본|정보)$/.test(t))
        for (let p = e.parentElement, k = 0; p && k < 3; p = p.parentElement, k++)
          if (p.querySelector('img') && p.getBoundingClientRect().height < 80) { e.classList.add('__tm_blur'); break; }
    }
    // 상세: 이름표(이름·생년월일…)와 같은 줄, 오른쪽 값
    for (const lab of leaves) {
      const w = (lab.innerText || '').trim(); if (!LABELS.includes(w)) continue;
      const a = lab.getBoundingClientRect(); if (a.x < 240 || a.width <= 0) continue;
      const cy = a.y + a.height / 2;
      for (const v of leaves) {
        const b = v.getBoundingClientRect(); if (b.width <= 0 || v === lab) continue;
        if (Math.abs(b.y + b.height / 2 - cy) < 14 && b.x > a.x + 60 && b.x < a.x + 520 && (v.innerText || '').trim())
          v.classList.add('__tm_blur');
      }
    }
  };
  setInterval(run, 80);
})()"""


class Ep21Recorder(E20.Ep20Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR21)
        super().scenario()

    def row(self):
        """목록 첫 사범님 줄 상자."""
        hd = self.leaf("담당반")
        if not hd:
            raise SceneError(self.scene, "사범 목록", "목록을 찾지 못했어요")
        return self.rect(262, hd["y"] + 32, 1630, 60), hd

    # ── 1단계: 사범 목록 보기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "도장 관리", "사범", LIST_URL)
        self.pg.get_by_text("담당반", exact=True).first.wait_for(timeout=15000)
        self.sleep(0.4)

    def do_M1(self, s, end):                       # 목록 전체
        r, hd = self.row()
        box = self.rect(262, hd["y"] - 30, 1630, r["y"] + r["height"] - (hd["y"] - 30))
        self.spot(box, self.now(), end + 0.2, 0)
        self.glide(r["x"] + 120, r["y"] + 30, 0.9)
        self.wait_until(end - 0.1)

    def do_M2(self, s, end):                       # 단 → 휴대전화 → 입사일 → 담당반
        r, hd = self.row()
        self.spot(self.rect(560, hd["y"] - 30, 760, r["y"] + r["height"] - (hd["y"] - 30)), self.now(), end + 0.2, 0)
        step = max(0.5, self.dur[s.key] / 5)
        for w in ("단", "휴대전화", "입사일", "담당반"):
            h = self.leaf(w, ymax=300)
            if h:
                self.glide(h["x"] + 20, r["y"] + 30, step * 0.7)
                self.sleep(step * 0.3)
        self.wait_until(end - 0.1)

    def do_M3(self, s, end):                       # 반 선택 칸 열어 보여 주고 닫기(고르지 않음)
        pg = self.pg
        sel = self.box_of(pg.locator(".MuiSelect-select").first)
        self.spot(self.rect(sel["x"] - 6, sel["y"] - 6, sel["width"] + 12, sel["height"] + 12), self.now(), self.now() + 1.6, 4)
        self.go_click(sel, 0.8)
        self.sleep(0.5)
        opts = pg.locator("li[role=option]")
        if opts.count():
            ob = self.union(*[self.box_of(opts.nth(i)) for i in range(min(opts.count(), 6))], pad=6)
            self.spot(ob, self.now(), end - 0.2, 4)
            self.glide(ob["x"] + 100, ob["y"] + ob["height"] * 0.6, 0.8)
        self.wait_until(end - 0.4)
        pg.keyboard.press("Escape")
        self.sleep(0.4)

    # ── 2단계: 사범 정보 보기 ──
    def do_D1(self, s, end):
        pg = self.pg
        r, _ = self.row()
        self.spot(r, self.now(), self.now() + max(1.6, self.dur[s.key] * 0.6), 0)
        self.sleep(max(0.5, self.dur[s.key] * 0.3))
        self.go_click(self.rect(r["x"] + 1200, r["y"] + r["height"] / 2 - 5, 10, 10), 0.8)
        pg.wait_for_url("**/manage/sabum/detail**", timeout=15000)
        pg.get_by_text("기본 정보", exact=True).first.wait_for(timeout=15000)
        self.sleep(0.8)
        self.spin_wait()

    def do_D2(self, s, end):                       # 기본 정보 → 단
        a = self.leaf("기본 정보")
        dan = self.leaf("태권도 정보")
        self.spot(self.rect(a["x"] - 16, a["y"] - 14, 1600, dan["y"] - a["y"] - 10), self.now(), self.now() + max(1.8, self.dur[s.key] * 0.55), 0)
        self.glide(a["x"] + 230, a["y"] + 120, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        d = self.leaf("단")
        if d:
            self.spot(self.rect(d["x"] - 16, dan["y"] - 14, 900, d["y"] + 50 - dan["y"] + 14), self.now(), end + 0.2, 0)
            self.glide(d["x"] + 200, d["y"] + d["height"] / 2, 0.8)
        self.wait_until(end - 0.1)

    def do_D3(self, s, end):                       # 학력·자격증·수상·경력 천천히 내리기
        pg = self.pg
        h = pg.evaluate("document.documentElement.scrollHeight")
        bottom = max(0, h - 1080)
        n = 3
        per = max(0.8, (self.dur[s.key] - 0.4) / n)
        for i in range(1, n + 1):
            self.scroll_to(bottom * i / (n + 0.6), per * 0.6)
            self.glide(700, 520 + (i % 2) * 120, per * 0.35)
        self.wait_until(end - 0.1)

    # ── 3단계: 퇴사 정리하기 ──
    def do_X1(self, s, end):                       # 맨 아래 퇴사(가리키기만)
        pg = self.pg
        h = pg.evaluate("document.documentElement.scrollHeight")
        self.scroll_to(max(0, h - 1080), 0.8)
        self.sleep(0.3)
        b = self.box_of(pg.get_by_text("퇴사", exact=True).last)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 14, b["y"] - 10, b["width"] + 28, b["height"] + 20), self.now() - 0.4, end + 0.2, 0)
        self.wait_until(end - 0.2)

    def do_X2(self, s, end):                       # 위로 → ← 눌러 목록으로
        pg = self.pg
        self.scroll_to(0, 0.6)
        self.sleep(0.2)
        b = self.rect(262, 30, 22, 22)
        self.glide(b["x"] + 11, b["y"] + 11, 0.7)
        self.spot(self.rect(256, 22, 130, 38), self.now() - 0.3, self.now() + 1.2, 4)
        self.wait_until(end - 0.8)
        self.click()
        pg.wait_for_url(f"**{LIST_URL}**", timeout=15000)
        pg.get_by_text("담당반", exact=True).first.wait_for(timeout=15000)
        self.sleep(0.6)


maker.Recorder = Ep21Recorder


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

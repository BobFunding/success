"""24편(도장 정보) 만들기: 23편 녹화기(메뉴·글자 찾기·ghost 줌) + 이 편만의 동작.
사용: python run_ep24.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 저장·도장 삭제는 절대 누르지 않고 가리키기만 한다. 요청도 막는다.
- 흐림: 도장 전화번호·주소·사업자 등록번호·등록증 파일 이름·직인(이 편), 도장 선택 화면의 다른 도장 카드와 우리 도장 번호·주소(2편 규칙).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
for d in ("ep23", "ep22", "ep21", "ep20", "ep16"):
    sys.path.insert(0, str(HERE.parent / d))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep23 as E23                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

MY = "태권월드 태권도장"

BLUR24 = r"""(() => {
  const run = () => {
    if (!/\/manage\/dojang/.test(location.pathname)) return;
    for (const n of ['phone_number', 'road_address', 'address_detail', 'BR_number'])
      for (const i of document.querySelectorAll(`input[name="${n}"]`)) i.classList.add('__tm_blur');
    for (const i of document.querySelectorAll('input[placeholder="파일을 업로드 해주세요."]')) i.classList.add('__tm_blur');
    for (const im of document.querySelectorAll('img, canvas, div')) {     // 직인(오른쪽 아래, 배경 그림 div)
      if (im.tagName === 'DIV' && !getComputedStyle(im).backgroundImage.includes('url')) continue;
      const r = im.getBoundingClientRect(); if (r.x > 950 && r.y > 380 && r.width > 60) im.style.setProperty('filter', 'blur(12px)', 'important'); }
  };
  setInterval(run, 80);
})()"""


class Ep24Recorder(E23.Ep23Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR24)
        super().scenario()

    def lab(self, word):
        b = self.leaf(word)
        if not b:
            loc = self.pg.get_by_text(word, exact=True).first
            b = self.box_of(loc) if loc.count() else None
        if not b:
            raise SceneError(self.scene, word, "화면에서 찾지 못했어요")
        return b

    def card(self):
        """도장 선택 화면에서 우리 도장 카드."""
        return self.pg.locator("div[slide]").filter(has=self.pg.locator("p", has_text=MY)).first

    # ── 1단계 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "도장 관리", "도장", "/manage/dojang")
        self.pg.locator("input[name=dojang_name]").wait_for(timeout=15000)
        self.sleep(0.6)

    def do_E1(self, s, end):                       # 이름·전화번호·주소
        a, z = self.lab("도장 이름"), self.pg.locator("input[name=address_detail]")
        zb = self.box_of(z)
        box = self.rect(a["x"] - 14, a["y"] - 24, zb["x"] + zb["width"] - a["x"] + 28, zb["y"] + zb["height"] - a["y"] + 40)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / 3.5)
        for n in ("dojang_name", "phone_number", "road_address"):
            b = self.box_of(self.pg.locator(f"input[name={n}]"))
            self.glide(b["x"] + 80, b["y"] + b["height"] / 2, step * 0.6)
            self.sleep(step * 0.4)
        self.wait_until(end - 0.1)

    def do_E2(self, s, end):                       # 사업자 등록번호·등록증
        a = self.lab("사업자 등록번호")
        up = self.box_of(self.pg.get_by_role("button", name="파일 업로드").first)
        box = self.rect(a["x"] - 14, a["y"] - 24, up["x"] + up["width"] - a["x"] + 28, up["y"] + up["height"] - a["y"] + 60)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        n = self.box_of(self.pg.locator("input[name=BR_number]"))
        self.glide(n["x"] + 100, n["y"] + n["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(up["x"] - 200, up["y"] + up["height"] / 2, 0.8)
        self.wait_until(end - 0.1)

    def do_E3(self, s, end):                       # 로고·직인
        a, b = self.lab("도장 로고"), self.lab("도장 직인")
        box = self.rect(a["x"] - 14, a["y"] - 20, 1400, 200)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        self.glide(a["x"] + 400, a["y"] + 80, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(b["x"] + 400, b["y"] + 80, 0.8)
        self.wait_until(end - 0.1)

    def do_E4(self, s, end):                       # 저장(가리키기만)
        b = self.box_of(self.pg.get_by_role("button", name="저장", exact=True).first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.1)

    # ── 2단계 ──
    def do_C1(self, s, end):                       # 왼쪽 위 ⋮
        b = self.rect(197, 63, 20, 20)
        self.glide(207, 73, 0.9)
        self.spot(self.rect(60, 55, 170, 110), self.now() - 0.3, end + 0.2, 6)
        self.wait_until(end - 0.4)
        self.click()
        self.pg.get_by_text("등록된 도장 보기").first.wait_for(timeout=5000)
        self.sleep(0.3)

    def do_C2(self, s, end):                       # 등록된 도장 보기 → 도장 선택 화면
        pg = self.pg
        b = self.box_of(pg.get_by_text("등록된 도장 보기").first)
        self.go_click(b, 0.7)
        self.nozoom()
        pg.wait_for_url("**/dojang/select", timeout=20000)
        pg.locator("div[slide]").first.wait_for(timeout=20000)
        self.sleep(1.0)
        c = self.box_of(self.card())
        cards = self.rect(c["x"] - 6, c["y"] - 6, 1512, c["height"] + 12)
        self.spot(cards, self.now(), end + 0.2, 0)
        self.glide(c["x"] + 700, c["y"] + 300, 0.9)
        self.wait_until(end - 0.1)

    def do_C3(self, s, end):                       # 관리하러 가기(가리키기만)
        b = self.box_of(self.card().get_by_text("관리하러 가기").first)
        c = self.box_of(self.card())
        self.spot(c, self.now(), self.now() + max(1.2, self.dur[s.key] * 0.4), 0)
        self.look(c, end - self.now())
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() + 0.4, end + 0.2, 6)
        self.wait_until(end - 0.1)

    # ── 3단계 ──
    def do_X1(self, s, end):                       # 카드 ⋮ → 삭제(가리키기만) → 빈 곳 눌러 닫기
        pg = self.pg
        c = self.box_of(self.card())
        dots = self.rect(c["x"] + c["width"] - 44, c["y"] + 20, 26, 26)
        self.look(self.rect(c["x"], c["y"], c["width"], 300), end - self.now())
        self.go_click(dots, 0.8)
        self.nozoom()
        d = pg.get_by_text("삭제", exact=True).first
        d.wait_for(timeout=5000)
        self.sleep(0.3)
        db = self.box_of(d)
        self.glide(db["x"] + db["width"] / 2, db["y"] + db["height"] / 2, 0.6)       # 가리키기만(누르지 않음)
        self.spot(self.rect(db["x"] - 30, db["y"] - 10, db["width"] + 60, db["height"] + 20), self.now() - 0.3, end - 0.4, 6)
        self.wait_until(end - 0.5)
        self.glide(960, 960, 0.3)                  # 빈 곳(카드 아래)을 눌러 닫기
        self.click()
        self.nozoom()
        self.sleep(0.2)
        if pg.get_by_text("삭제", exact=True).first.is_visible():
            raise SceneError(s, "삭제", "삭제 메뉴가 닫히지 않았어요")

    def do_X2(self, s, end):                       # 소속 사범님 수·수련생 수
        a = self.box_of(self.card().get_by_text("소속 사범님 수").first)
        c = self.box_of(self.card())
        box = self.rect(c["x"] + 24, a["y"] - 18, c["width"] - 48, 110)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(self.rect(c["x"], a["y"] - 120, c["width"], 300), end - self.now())
        self.glide(a["x"] + 160, a["y"] + a["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        self.glide(a["x"] + 160, a["y"] + 51 + a["height"] / 2, 0.6)
        self.wait_until(end - 0.1)


maker.Recorder = Ep24Recorder


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

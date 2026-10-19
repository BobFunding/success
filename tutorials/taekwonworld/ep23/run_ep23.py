"""23편(초대장 관리) 만들기: 22편 녹화기(메뉴·글자 찾기) + 이 편만의 동작.
사용: python run_ep23.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 삭제·초대장 발송은 가리키기만 한다. 요청도 막는다(요청차단 /invitation).
- 흐림: 받는 사람 이름(사진 옆), 전화번호.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
for d in ("ep22", "ep21", "ep20", "ep16"):
    sys.path.insert(0, str(HERE.parent / d))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep22 as E22                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

LIST_URL = "/invitation/inquiry"

BLUR23 = r"""(() => {
  const skip = /^(수련생|사범|관장|학부모|가족|관계|상태|삭제|조회)$/;
  const run = () => {
    if (!/\/invitation/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim(); if (!t) continue;
      if (/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(t)) { e.classList.add('__tm_blur'); continue; }
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t) || e.closest('button')) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, k = 0; p && k < 4; p = p.parentElement, k++)
        if (p.querySelector('img')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 80);
})()"""


class Ep23Recorder(E22.Ep22Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR23)
        super().scenario()

    def look(self, b, hold):
        """누르지 않고 b 자리로 줌(19편과 같음): 줄이 하나뿐인 표를 크게 보여 줄 때."""
        from autoedit.tutorial.recorder import SCALE
        z = max(1.0, min(1.8, 0.85 * 1920 / (b["width"] + 40), 0.85 * 1080 / (b["height"] + 40)))
        self.log["clicks"].append({"t": round(self.now(), 3), "x": (b["x"] + b["width"] / 2) * SCALE,
                                   "y": (b["y"] + b["height"] / 2) * SCALE, "ghost": True, "hold": round(hold, 2), "zoom": round(z, 2)})

    def head(self, word):
        h = self.leaf(word, ymax=200)
        if not h:                                  # 정렬 화살표가 붙은 머리글은 자식이 있어 leaf 로 안 잡힘
            loc = self.pg.get_by_text(word, exact=True).first
            h = self.box_of(loc) if loc.count() else None
        if not h:
            raise SceneError(self.scene, word, "목록 칸을 찾지 못했어요")
        return h

    def col(self, s, end, words, w):
        """목록 머리글 words[0] 부터 너비 w 만큼, 머리글~첫 줄을 밝게 하고 칸마다 짚기."""
        a = self.head(words[0])
        box = self.rect(a["x"] - 16, a["y"] - 20, w, 128)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(self.rect(box["x"] - 200, box["y"], max(w, 700) + 200, 300), end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / (len(words) + 0.5))
        for word in words:
            h = self.head(word)
            self.glide(h["x"] + 30, h["y"] + 62, step * 0.6)
            self.sleep(step * 0.4)
        self.wait_until(end - 0.1)

    # ── 1단계 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "초대장", "조회", LIST_URL)
        self.pg.get_by_text("초대장 만료일").first.wait_for(timeout=15000)
        self.sleep(0.4)

    def do_M1(self, s, end):
        a = self.head("관계")
        self.spot(self.rect(262, a["y"] - 30, 1630, 124), self.now(), end + 0.2, 0)
        self.look(self.rect(262, a["y"] - 60, 1300, 320), end - self.now())
        self.glide(400, a["y"] + 62, 0.9)
        self.wait_until(end - 0.1)

    # ── 2단계 ──
    def do_S1(self, s, end):
        a = self.leaf("수련생/사범님", ymax=200) or self.head("관계")
        self.spot(self.rect(262, a["y"] - 30, 640, 124), self.now(), end + 0.2, 0)
        self.look(self.rect(262, a["y"] - 60, 900, 300), end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / 3.5)
        for x in (330, 600, 760):
            self.glide(x, a["y"] + 62, step * 0.6)
            self.sleep(step * 0.4)
        self.wait_until(end - 0.1)

    def do_S2(self, s, end):
        self.col(s, end, ["상태"], 480)

    def do_S3(self, s, end):
        self.col(s, end, ["초대장 만료일"], 240)

    # ── 3단계 ──
    def point(self, s, end, b, pad=8):
        self.look(self.rect(b["x"] + b["width"] - 900, b["y"] - 120, 900, 300), end - self.now())
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(self.rect(b["x"] - pad, b["y"] - pad, b["width"] + pad * 2, b["height"] + pad * 2), self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.1)

    def do_D1(self, s, end):                       # 삭제(가리키기만)
        self.point(s, end, self.box_of(self.pg.get_by_role("button", name="삭제", exact=True).first))

    def do_D2(self, s, end):                       # 초대장 발송(가리키기만)
        self.point(s, end, self.box_of(self.pg.get_by_role("button", name="초대장 발송").first))

    def do_D3(self, s, end):
        self.do_M1(s, end)


maker.Recorder = Ep23Recorder


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

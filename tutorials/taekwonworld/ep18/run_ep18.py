"""18편(도장 홈페이지) 만들기: 16편 녹화기(메뉴·창 닫기 nozoom) + 이 편만의 동작.
사용: python run_ep18.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 1단계 안내 화면(phone/why.html): 도장 홈페이지가 왜 필요한지(사용자 요청: '왜 하려고 하는지' 맥락).
- 데모 도장 홈페이지는 지금 닫혀 있어 사이트는 열지 않는다. 태권월드 '도장 홈페이지' 메뉴의 주소·ARS·QR·관리안내 그림으로 설명한다.
- 주소 링크·QR 은 가리키기만 한다(누르면 새 창·내려받기).
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

WHY = (HERE / "phone" / "why.html").as_uri()
HOME = "https://taekwonworld.net/home"


class Ep18Recorder(E16.Ep16Recorder):
    def card(self, s, end, hot, rows=False):
        pg = self.pg
        if not pg.url.startswith(WHY):
            pg.goto(WHY, wait_until="load")
            pg.wait_for_timeout(1200)
        h = self.box_of(pg.locator(f"#{hot}"))
        self.spot(self.rect(h["x"] - 8, h["y"] - 8, h["width"] + 16, h["height"] + 16), self.now(), end + 0.2, 0)
        self.glide(h["x"] + h["width"] * 0.5, h["y"] + h["height"] * 0.4, 0.9)
        if rows:
            for y in (0.35, 0.6, 0.85):
                self.glide(h["x"] + h["width"] * 0.3, h["y"] + h["height"] * y, max(0.6, self.dur[s.key] * 0.2))

    def row_box(self, label, right=900, pad_y=18):
        """'홈페이지 도메인' 같은 왼쪽 이름표부터 오른쪽 내용까지 한 줄."""
        a = self.leaf(label)
        if not a:
            raise SceneError(self.scene, label, "화면에서 찾지 못했어요")
        return a, self.rect(a["x"] - 20, a["y"] - pad_y, right, a["height"] + pad_y * 2)

    def guide_img(self, i):
        """관리안내 그림 i 번째(0부터) — 화면에 보이는 위치."""
        b = self.pg.evaluate("""(i) => { const imgs=[...document.querySelectorAll('img')].filter(e=>{const r=e.getBoundingClientRect(); return r.width>250 && r.x>400;})
              .sort((a,b)=>a.getBoundingClientRect().top - b.getBoundingClientRect().top);
            const qr = imgs.findIndex(e=>Math.abs(e.getBoundingClientRect().width - e.getBoundingClientRect().height) < 8);
            const g = imgs.filter((e,k)=>k!==qr); const e=g[i]; if(!e) return null; const r=e.getBoundingClientRect();
            return {x:r.x, y:r.y, width:r.width, height:r.height, top:r.top + scrollY}; }""", i)
        if not b:
            raise SceneError(self.scene, "관리안내 그림", "그림을 찾지 못했어요")
        return b

    # ── 1단계: 왜 필요할까요 ──
    def do_Y1(self, s, end):
        self.card(s, end, "hot-a")

    def do_Y2(self, s, end):
        self.card(s, end, "hot-b", rows=True)
        self.wait_until(end)
        self.pg.goto(HOME, wait_until="domcontentloaded")          # 문장 사이: 첫 화면(안내 창)으로
        self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
        self.sleep(0.6)

    # ── 2단계: 주소와 QR 확인하기 ──
    def do_P2(self, s, end):                       # 왼쪽 메뉴 '도장 홈페이지'(하위 메뉴 없음)
        pg = self.pg
        it = self.side("도장 홈페이지")
        if not it:
            raise SceneError(s, "도장 홈페이지", "왼쪽 메뉴에서 찾지 못했어요")
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(it["x"] + 90, it["y"] + it["height"] / 2, 0.8)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url("**/hp", timeout=20000)
        pg.get_by_text("홈페이지 QR").first.wait_for(timeout=15000)
        self.sleep(0.5)

    def do_A1(self, s, end):                       # 홈페이지 주소(가리키기만)
        a, row = self.row_box("홈페이지 도메인")
        link = self.box_of(self.pg.locator("a[href*='taekwonworld.net']").filter(has_text="taekwonworld").first)
        self.spot(row, self.now(), end + 0.2, 0)
        self.glide(a["x"] + 60, a["y"] + a["height"] / 2, 0.7)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(link["x"] + link["width"] / 2, link["y"] + link["height"] / 2, 0.8)
        self.wait_until(end - 0.1)

    def do_A2(self, s, end):                       # ARS
        a, row = self.row_box("홈페이지 ARS", right=900, pad_y=18)
        row["height"] += 34                        # 아래 안내 한 줄까지
        self.spot(row, self.now(), end + 0.2, 0)
        self.glide(a["x"] + 60, a["y"] + a["height"] / 2, 0.7)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(a["x"] + 420, a["y"] + a["height"] / 2, 0.9)
        self.wait_until(end - 0.1)

    def do_A3(self, s, end):                       # QR(가리키기만)
        a = self.leaf("홈페이지 QR")
        qr = self.pg.evaluate("""() => { const e=[...document.querySelectorAll('img, canvas, svg')].find(e=>{const r=e.getBoundingClientRect(); return r.width>100 && Math.abs(r.width-r.height)<8 && r.x>400;});
            if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x, y:r.y, width:r.width, height:r.height}; }""")
        if not (a and qr):
            raise SceneError(s, "홈페이지 QR", "QR 코드를 찾지 못했어요")
        box = self.rect(a["x"] - 20, a["y"] - 18, 900, qr["y"] + qr["height"] + 70 - (a["y"] - 18))
        self.spot(box, self.now(), end + 0.2, 0)
        self.glide(qr["x"] + qr["width"] / 2, qr["y"] + qr["height"] / 2, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(qr["x"] + 200, qr["y"] + qr["height"] + 30, 0.8)
        self.wait_until(end - 0.1)

    # ── 3단계: 홈페이지 관리하기 ──
    def manage(self, s, end, i):
        g = self.guide_img(i)
        want = max(0, g["top"] - 150)               # 그림이 화면 위쪽에 오게 굴리기
        self.scroll_to(want, 0.8)
        self.sleep(0.3)
        g = self.guide_img(i)
        self.spot(self.rect(g["x"] - 10, g["y"] - 52, max(g["width"] + 20, 860), g["height"] + 62), self.now(), end + 0.2, 0)
        self.glide(g["x"] + g["width"] * 0.3, g["y"] + g["height"] * 0.5, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(g["x"] + g["width"] * 0.6, g["y"] + g["height"] * 0.7, 0.8)
        self.wait_until(end - 0.1)

    def do_G1(self, s, end): self.manage(s, end, 0)
    def do_G2(self, s, end): self.manage(s, end, 1)
    def do_G3(self, s, end): self.manage(s, end, 2)


maker.Recorder = Ep18Recorder


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

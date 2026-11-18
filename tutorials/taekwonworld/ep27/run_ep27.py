"""27편(서비스 문의·사용자 가이드) 만들기: 25편 녹화기(메뉴·가이드 닫기·글자 찾기·ghost 줌) + 이 편만의 동작.
사용: python run_ep27.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 문의는 예시 문장만 적고 등록은 누르지 않는다(요청차단 /service).
- 사용자 가이드는 원래 새 창(탭)으로 열리지만 녹화 화면을 벗어나지 않도록 같은 창에서 열게 바꿔 둔다.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
for d in ("ep25", "ep24", "ep23", "ep22", "ep21", "ep20", "ep16"):
    sys.path.insert(0, str(HERE.parent / d))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep25 as E25                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

GUIDE = "https://taekwonworld.net/guide"
SAMPLE = "출석 QR 코드를 새로 받고 싶어요. 방법을 알려 주세요."

SAME_TAB = r"""(() => {                       // 새 창(탭) 대신 같은 창에서 열기(녹화 화면 유지)
  window.open = (u) => { if (u) location.href = u; return window; };
  document.addEventListener('click', (e) => { const a = e.target.closest && e.target.closest('a[target]'); if (a) a.removeAttribute('target'); }, true);
})()"""


class Ep27Recorder(E25.Ep25Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(SAME_TAB)
        super().scenario()

    def side_click(self, s, end, word, url_part):
        pg = self.pg
        it = self.side(word)
        if not it:
            raise SceneError(s, word, "왼쪽 메뉴에서 찾지 못했어요")
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(it["x"] + 90, it["y"] + it["height"] / 2, 0.8)
        self.spot(it, self.now() - 0.4, end + 0.1, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url(f"**{url_part}**", timeout=20000)
        self.sleep(0.6)

    # ── 1단계 ──
    def do_N1(self, s, end):
        self.side_click(s, end, "서비스 문의", "/service/inquiry")
        self.pg.locator("textarea[name=q_content]").wait_for(timeout=15000)

    def do_N2(self, s, end):                       # 문의 유형 열고 '계정' 고르기(화면 안에서만)
        pg = self.pg
        sel = self.box_of(pg.locator("input[name=q_type_cd]").locator("xpath=..").first)
        a = self.lab("문의 유형")
        box = self.rect(a["x"] - 14, sel["y"] - 14, sel["x"] + sel["width"] - a["x"] + 28, sel["height"] + 28)
        self.look(self.rect(box["x"], box["y"] - 40, 900, 420), end - self.now())
        self.spot(box, self.now(), self.now() + 1.4, 0)
        self.go_click(sel, 0.8)
        self.nozoom()
        opts = pg.locator("li[role=option]")
        opts.first.wait_for(timeout=5000)
        ob = self.union(*[self.box_of(opts.nth(i)) for i in range(opts.count())], pad=6)
        self.spot(ob, self.now(), end - 0.5, 4)
        self.glide(ob["x"] + 80, ob["y"] + 20, 0.5)
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        acc = self.box_of(pg.locator("li[role=option]", has_text="계정").first)
        self.wait_until(end - 0.9)
        self.go_click(acc, 0.5)
        self.nozoom()
        self.sleep(0.3)

    def do_N3(self, s, end):                       # 내용 적기 → 등록(가리키기만)
        pg = self.pg
        t = self.box_of(pg.locator("textarea[name=q_content]"))
        self.look(self.rect(t["x"] - 160, t["y"] - 40, 1000, 300), max(1.0, self.dur[s.key] * 0.55))
        self.spot(self.rect(t["x"] - 8, t["y"] - 8, t["width"] + 16, t["height"] + 16), self.now(), self.now() + max(1.5, self.dur[s.key] * 0.55), 0)
        self.glide(t["x"] + 60, t["y"] + 40, 0.6)
        self.typ("textarea[name=q_content]", SAMPLE, 0.045)
        self.nozoom()
        b = self.box_of(pg.get_by_role("button", name="등록", exact=True).first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)                # 가리키기만
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.3, end + 0.2, 6)
        self.wait_until(end - 0.1)

    # ── 2단계 ──
    def do_G1(self, s, end):                       # 사용자 가이드(같은 창으로)
        self.side_click(s, end, "사용자 가이드", "/guide")
        self.pg.get_by_text("알고싶은 기능을 클릭해주세요.").first.wait_for(timeout=20000)
        self.sleep(0.6)

    def do_G2(self, s, end):                       # 기능 카드 → 설명 페이지
        pg = self.pg
        h = pg.evaluate("document.documentElement.scrollHeight")
        card = pg.get_by_text("수련생 등록 & 조회 & 수정 & 퇴소하기").first
        top = card.evaluate("e => e.getBoundingClientRect().top + scrollY")
        self.scroll_to(max(0, min(h - 1080, top - 420)), 1.0)
        self.sleep(0.3)
        b = self.box_of(card)
        self.spot(self.rect(b["x"] - 24, b["y"] - 24, 300, 88), self.now(), self.now() + 1.4, 4)
        self.go_click(b, 0.8)
        self.nozoom()
        pg.wait_for_url("**/guide/kwanjang/**", timeout=20000)
        pg.get_by_text("수련생 등록하기").first.wait_for(timeout=15000)
        self.sleep(0.5)
        rest = max(0.8, end - self.now() - 0.2)
        self.glide(700, 420, rest * 0.4)
        self.scroll_to(300, rest * 0.5)
        self.wait_until(end - 0.1)

    def do_G3(self, s, end):                       # 언어 고르기 칸(가리키기만)
        self.scroll_to(0, 0.5)
        b = self.box_of(self.pg.get_by_text("한국어", exact=True).first)
        b = self.rect(b["x"] - 40, b["y"] - 10, b["width"] + 90, b["height"] + 20)
        self.look(self.rect(b["x"] - 500, b["y"] - 20, 700, 300), end - self.now())
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(b, self.now() - 0.3, end + 0.2, 6)
        self.wait_until(end - 0.1)
        self.pg.goto("https://taekwonworld.net/home", wait_until="domcontentloaded")    # 문장 사이: 관리 화면으로
        self.pg.locator("text=수련생").first.wait_for(timeout=30000)
        self.sleep(1.0)
        for _ in range(3):                         # 첫 화면 안내 창이 다시 뜨면 닫기(영상엔 문장 사이)
            if self.pg.locator(".MuiModal-root").count():
                c = self.pg.get_by_text("창 닫기", exact=True)
                (c.last.click() if c.count() else self.pg.keyboard.press("Escape"))
                self.sleep(0.5)

    # ── 3단계 ──
    def do_Y1(self, s, end):
        self.menu_go(s, end, "수련생", "전체 조회", "/manage/student/list")
        self.pg.get_by_text("휴관 등록 사용 가이드").first.wait_for(timeout=15000)

    def do_Y2(self, s, end):
        self.close_guide(s, end, "수련생 조회 - 휴관 등록 사용 가이드")

    def do_Y3(self, s, end):                       # 제목 옆 '사용 가이드' → 다시 열림 → 닫기
        pg = self.pg
        l = self.box_of(pg.get_by_text("사용 가이드", exact=True).first)
        self.look(self.rect(l["x"] - 200, l["y"] - 20, 700, 300), max(1.2, self.dur[s.key] * 0.5))
        self.spot(self.rect(l["x"] - 8, l["y"] - 6, l["width"] + 16, l["height"] + 12), self.now(), self.now() + max(1.2, self.dur[s.key] * 0.5), 4)
        self.sleep(max(0.3, self.dur[s.key] * 0.2))
        self.go_click(l, 0.8)
        self.nozoom()
        pg.get_by_text("휴관 등록 사용 가이드").first.wait_for(timeout=10000)
        self.wait_until(end - 0.1)


maker.Recorder = Ep27Recorder


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

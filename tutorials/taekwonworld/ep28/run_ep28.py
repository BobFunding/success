"""28편(로그아웃·회원 탈퇴) 만들기: 25편 녹화기(프로필 창·내 정보 흐림·ghost 줌) + 이 편만의 동작.
사용: python run_ep28.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 탈퇴 확인 창의 '탈퇴하기'는 절대 누르지 않고 가리키기만, '취소'로 닫는다. /mypage 의 요청은 모두 막는다.
- 로그아웃은 마지막에 실제로 누른다(계정·자료는 바뀌지 않음).
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

POP = {"x": 16, "y": 48, "width": 236, "height": 176}         # ≡ 프로필 창 자리


class Ep28Recorder(E25.Ep25Recorder):
    def open_menu(self, s, end, hold):
        self.glide(28, 25, 0.9)
        self.spot(self.rect(10, 8, 36, 34), self.now() - 0.3, self.now() + 1.4, 6)
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.click()
        self.nozoom()
        self.pg.get_by_text("내 정보", exact=True).first.wait_for(timeout=5000)
        self.look(self.rect(0, 0, 760, 420), hold)
        self.sleep(0.3)
        self.spot(POP, self.now(), end + 0.2, 6)
        self.wait_until(end - 0.1)

    def word_box(self, w):
        b = self.box_of(self.pg.get_by_text(w, exact=True).first)
        return self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12)

    # ── 1단계 ──
    def do_A1(self, s, end):
        self.open_menu(s, end, end - self.now() + self.dur["A2"] + self.dur["W1"] * 0.6)

    def do_A2(self, s, end):                       # 로그아웃 위치(가리키기만)
        b = self.word_box("로그아웃")
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.7)
        self.spot(b, self.now() - 0.3, end + 0.2, 4)
        self.wait_until(end - 0.1)

    # ── 2단계 ──
    def do_W1(self, s, end):                       # 내 정보
        pg = self.pg
        b = self.word_box("내 정보")
        self.spot(b, self.now(), self.now() + 1.4, 4)
        self.sleep(max(0.3, self.dur[s.key] * 0.35))
        self.go_click(b, 0.6)
        self.nozoom()
        pg.wait_for_url("**/mypage/account", timeout=20000)
        pg.get_by_text("탈퇴하기", exact=True).first.wait_for(timeout=15000)
        self.sleep(0.6)

    def do_W2(self, s, end):                       # 탈퇴하기 → 확인 창
        pg = self.pg
        b = self.word_box("탈퇴하기")
        self.look(self.rect(b["x"] - 560, b["y"] - 240, 700, 360), max(1.2, self.dur[s.key] * 0.6))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, self.now() - 0.3, self.now() + 1.2, 4)
        self.wait_until(end - 0.5)
        self.click()
        self.nozoom()
        pg.locator(".MuiModal-root").filter(has_text="탈퇴하시겠습니까").last.wait_for(timeout=8000)
        self.sleep(0.4)

    def dialog(self):
        return self.pg.locator(".MuiModal-root").filter(has_text="탈퇴하시겠습니까").last

    def do_W3(self, s, end):                       # 확인 창 안내 + '탈퇴하기' 가리키기만(절대 누르지 않음)
        m = self.dialog()
        t0 = self.box_of(m.get_by_text("회원 탈퇴", exact=True).first)          # 창 크기: 제목~버튼을 묶어서
        bt = self.box_of(m.get_by_role("button", name="취소").first)
        bd = self.box_of(m.get_by_role("button", name="탈퇴하기").first)
        box = self.union(t0, bt, bd, pad=24)
        if box:
            self.spot(box, self.now(), end + 0.2, 6)
            self.look(self.rect(box["x"] - 60, box["y"] - 60, box["width"] + 120, box["height"] + 120), end - self.now() + self.dur["W4"])
        t = self.box_of(m.get_by_text("탈퇴할 경우", exact=False).first)
        self.glide(t["x"] + 40, t["y"] + t["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.4))
        d = self.box_of(m.get_by_role("button", name="탈퇴하기").first)
        self.glide(d["x"] + d["width"] / 2, d["y"] + d["height"] / 2, 0.8)             # 가리키기만
        self.wait_until(end - 0.1)

    def do_W4(self, s, end):                       # 취소로 닫기
        pg = self.pg
        m = self.dialog()
        c = self.box_of(m.get_by_role("button", name="취소").first)
        self.glide(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, 0.7)
        self.spot(self.rect(c["x"] - 6, c["y"] - 6, c["width"] + 12, c["height"] + 12), self.now() - 0.3, self.now() + 0.6, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.nozoom()
        self.sleep(0.4)
        if self.dialog().count():
            raise SceneError(s, "취소", "탈퇴 확인 창이 닫히지 않았어요")
        if "/mypage/account" not in pg.url:
            raise SceneError(s, "취소", "내 정보 화면이 아니에요")

    # ── 3단계 ──
    def do_L4(self, s, end):
        self.open_menu(s, end, end - self.now() + self.dur["L5"] * 0.7)

    def do_L5(self, s, end):                       # 실제 로그아웃
        pg = self.pg
        b = self.word_box("로그아웃")
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.7)
        self.spot(b, self.now() - 0.3, self.now() + 1.0, 4)
        self.wait_until(end - 0.8)
        self.click()
        self.nozoom()
        pg.wait_for_url(lambda u: "/mypage" not in u, timeout=20000)
        pg.locator("button:has-text('로그인(관장)')").first.wait_for(timeout=20000)   # 서비스 첫 화면이 다 뜰 때까지
        self.sleep(1.5)


maker.Recorder = Ep28Recorder


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

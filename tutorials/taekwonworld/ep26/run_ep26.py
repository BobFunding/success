"""26편(아이디·비밀번호 찾기) 만들기: 25편 녹화기(글자 찾기·ghost 줌) + 이 편만의 동작. 로그아웃 상태로 시작.
사용: python run_ep26.py check|make [작업폴더] [--silent]   (로그인하지 않으므로 계정 정보가 필요 없음)
- 휴대전화·아이디 칸에는 예시 값(가짜)을 적고 흐린다. 인증요청·인증확인·저장은 누르지 않는다. /account/find 의 요청은 모두 막는다.
"""
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

LOGIN = "https://taekwonworld.net/account/login"
PHONE = "01012345678"                                         # 예시 번호(흐림)
USER = "taekwon123"                                           # 예시 아이디(흐림)


class Ep26Recorder(E25.Ep25Recorder):
    def run_pre(self) -> None:                     # 로그아웃 상태로 시작: 3편의 미리 로그인을 건너뜀
        if self.sc.pre_scenes:
            super().run_pre()

    def at(self, loc, wait=8000):
        loc.first.wait_for(timeout=wait)
        return self.box_of(loc.first)

    def point(self, b, end, pad=8, look=True):
        if look:
            self.look(self.rect(b["x"] - 300, b["y"] - 150, 800, 360), end - self.now())
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - pad, b["y"] - pad, b["width"] + pad * 2, b["height"] + pad * 2), self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.1)

    def type_into(self, name, text, delay=0.07):
        sel = f"input[name={name}]"
        b = self.box(sel)
        self.glide(b["x"] + 40, b["y"] + b["height"] / 2, 0.6)
        self.typ(sel, text, delay)
        self.nozoom()

    # ── 1단계 ──
    def do_J1(self, s, end):                       # 첫 화면 → 로그인(관장)
        pg = self.pg
        b = self.at(pg.locator("button:has-text('로그인(관장)')"))
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.4, end + 0.1, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url("**/account/login", timeout=20000)
        pg.locator("input[name=username]").wait_for(timeout=15000)
        self.sleep(0.6)

    def do_J2(self, s, end):                       # 아이디 찾기 / 비밀번호 찾기 자리
        pg = self.pg
        a = self.at(pg.get_by_text("아이디 찾기", exact=True))
        z = self.at(pg.get_by_text("비밀번호 찾기", exact=True))
        box = self.rect(a["x"] - 10, a["y"] - 8, z["x"] + z["width"] - a["x"] + 20, a["height"] + 16)
        self.look(self.rect(box["x"] - 350, box["y"] - 200, 820, 440), end - self.now() + 1.0)
        self.spot(box, self.now(), end + 0.2, 4)
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        self.glide(z["x"] + z["width"] / 2, z["y"] + z["height"] / 2, 0.6)
        self.wait_until(end - 0.1)

    # ── 2단계 ──
    def do_U1(self, s, end):                       # 아이디 찾기 → 번호 적기
        pg = self.pg
        self.block_requests()
        a = self.at(pg.get_by_text("아이디 찾기", exact=True))
        self.go_click(a, 0.6)
        self.nozoom()
        pg.wait_for_url("**/account/find/username", timeout=20000)
        b = self.at(pg.locator("input[name=phone_number]"), 15000)
        self.sleep(0.5)
        self.look(self.rect(b["x"] - 200, b["y"] - 120, 640, 260), end - self.now() + self.dur["U2"])
        self.spot(self.rect(b["x"] - 120, b["y"] - 40, 520, b["height"] + 56), self.now(), end + 0.2, 0)
        self.type_into("phone_number", PHONE)
        self.wait_until(end - 0.1)

    def do_U2(self, s, end):                       # 인증요청(가리키기만)
        self.point(self.at(self.pg.get_by_role("button", name="인증요청")), end, look=False)

    def do_U3(self, s, end):                       # 인증번호 칸 → 인증확인(가리키기만)
        pg = self.pg
        n = self.at(pg.locator("input[name=number_by_user]"))
        c = self.at(pg.get_by_role("button", name="인증확인"))
        self.look(self.rect(n["x"] - 200, n["y"] - 140, 640, 280), end - self.now())
        self.spot(self.rect(n["x"] - 8, n["y"] - 34, c["x"] + c["width"] - n["x"] + 16, n["height"] + 42), self.now(), end + 0.2, 0)
        self.type_into("number_by_user", "1234", 0.12)
        self.sleep(0.3)
        self.glide(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, 0.7)       # 가리키기만
        self.wait_until(end - 0.1)

    def do_U4(self, s, end):                       # 다시 인증요청 가리키기
        self.point(self.at(self.pg.get_by_role("button", name="인증요청")), end)

    # ── 3단계 ──
    def do_Z1(self, s, end):                       # 로그인 화면으로 → 비밀번호 찾기
        pg = self.pg
        pg.goto(LOGIN, wait_until="domcontentloaded")                 # 문장 사이: 로그인 화면으로 돌아가기
        b = self.at(pg.get_by_text("비밀번호 찾기", exact=True), 20000)
        self.sleep(0.4)
        self.look(self.rect(b["x"] - 500, b["y"] - 200, 820, 440), end - self.now())
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now(), end + 0.2, 4)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.go_click(b, 0.7)
        self.nozoom()
        pg.wait_for_url("**/account/find/password", timeout=20000)
        pg.locator("input[name=new_password]").wait_for(timeout=15000)
        self.sleep(0.4)

    def do_Z2(self, s, end):                       # 아이디·휴대전화·인증번호
        pg = self.pg
        u = self.at(pg.locator("input[name=username]"))
        n = self.at(pg.locator("input[name=number_by_user]"))
        box = self.rect(u["x"] - 10, u["y"] - 40, u["width"] + 20, n["y"] + n["height"] - u["y"] + 50)
        self.look(self.rect(box["x"] - 100, box["y"] - 40, box["width"] + 200, box["height"] + 80), end - self.now())
        self.spot(box, self.now(), end + 0.2, 0)
        self.type_into("username", USER)
        self.type_into("phone_number", PHONE, 0.05)
        r = self.at(pg.get_by_role("button", name="인증요청"))
        self.glide(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2, 0.5)      # 가리키기만
        self.sleep(0.3)
        self.wait_until(end - 0.1)

    def do_Z3(self, s, end):                       # 새 비밀번호 두 번(점으로 보임)
        pg = self.pg
        a = self.at(pg.locator("input[name=new_password]"))
        z = self.at(pg.locator("input[name=chk_password]"))
        box = self.rect(a["x"] - 10, a["y"] - 40, a["width"] + 20, z["y"] + z["height"] - a["y"] + 50)
        self.look(self.rect(box["x"] - 100, box["y"] - 60, box["width"] + 200, box["height"] + 120), end - self.now())
        self.spot(box, self.now(), end + 0.2, 0)
        self.type_into("new_password", "Taekwon!2026", 0.06)
        self.type_into("chk_password", "Taekwon!2026", 0.06)
        self.wait_until(end - 0.1)

    def do_Z4(self, s, end):                       # 저장(가리키기만)
        self.point(self.at(self.pg.get_by_role("button", name="저장", exact=True)), end)


maker.Recorder = Ep26Recorder


def load():
    return S.load(HERE / "scenario.yaml")


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

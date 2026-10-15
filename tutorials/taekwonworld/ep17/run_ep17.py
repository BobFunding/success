"""17편(헬스케어) 만들기: 16편 녹화기(new 표시 메뉴·창 바깥 닫기·휴대폰) + 이 편만의 동작.
사용: python run_ep17.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- '헬스케어 테스트' 도장(측정 기록 있음)에서 찍는다. 도장 이름·로고·수련생 이름은 흐린다.
- 1단계 안내 화면(phone/info.html): 헬스케어는 셀바스 아큐닉 BC380 PLUS 를 구매해야 연동된다(사용자 요청).
- 읽기만 한다. 아큐닉 대시보드(바깥 사이트)는 가리키기만 하고 열지 않는다.
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep16"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep16 as E16                                        # noqa: E402
from run_ep16 import maker, S, SceneError, E12                # noqa: E402

E12.PHONE = (HERE / "phone" / "phone.html").as_uri()          # 12편 phone() 이 이 편 휴대폰 화면을 연다
INFO = (HERE / "phone" / "info.html").as_uri()
DOJANG = "헬스케어 테스트"
HOME = "https://taekwonworld.net/home"
# 측정 기록 날짜(2024년)를 오늘(2026-10-15) 기준으로 옮겨 보여 준다(녹화 브라우저 안에서만, 서버는 그대로).
# 앱 캡처와 같은 기준: 가장 최근 기록 2024-11-22 → 2026-10-15, 오늘보다 뒤로 가는 날짜는 오늘로.
TODAY = dt.date(2026, 10, 15)
SHIFT = TODAY - dt.date(2024, 11, 22)


def _move(y, m, d):
    try:
        return min(dt.date(int(y), int(m), int(d)) + SHIFT, TODAY)
    except ValueError:
        return None


def redate(text: str) -> str:
    def dash(mt):
        n = _move(*mt.groups()); return n.isoformat() if n else mt.group(0)
    def plain(mt):
        n = _move(*mt.groups()); return n.strftime("%Y%m%d") if n else mt.group(0)
    text = re.sub(r"(2024)-(\d{2})-(\d{2})", dash, text)
    return re.sub(r"(?<!\d)(2024)(\d{2})(\d{2})(?!\d)", plain, text)

# 헬스케어 테스트 도장: 도장 이름·로고, 사진 옆 수련생 이름 흐림
BLUR17 = r"""(() => {
  const skip = /조회|선택|전체|수련생|측정|반$|띠$/;
  const run = () => {
    for (const i of document.querySelectorAll('img[src*="dojang/logo"]')) i.classList.add('__tm_blur');
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (t === '헬스케어 테스트') { e.classList.add('__tm_blur'); continue; }
      if (!/\/healthcare/.test(location.pathname)) continue;
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t) || e.closest('button')) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, i = 0; p && i < 4; p = p.parentElement, i++)
        if (p.querySelector('img')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 80);
})()"""


class Ep17Recorder(E16.Ep16Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR17)
        super().scenario()

    def run_pre(self) -> None:
        """로그인 뒤 '헬스케어 테스트' 도장으로 들어가 첫 화면까지(영상 밖)."""
        pg = self.pg
        ps = self.sc.pre_scenes[0]
        self.scene = ps
        pg.goto(self.sc.login_url, wait_until="domcontentloaded", timeout=60000)
        for f in ps.fields:
            self.locate(f.target).fill(self.resolve_value(f), timeout=30000)
        self.locate(ps.button).click(timeout=10000)
        try:
            pg.wait_for_url(lambda u: "/account/login" not in u, timeout=30000)
        except Exception:
            raise SceneError(ps, "로그인", "로그인에 실패했어요. 보관함의 비밀번호를 확인해 주세요") from None
        pg.goto("https://taekwonworld.net/dojang/select", wait_until="domcontentloaded")
        card = pg.locator("div[slide]").filter(has=pg.locator("p", has_text=DOJANG)).first
        card.wait_for(timeout=30000)
        card.get_by_text("관리하러 가기").click(timeout=20000)
        pg.wait_for_url("**/home", timeout=30000)
        self.scene = None

    def block_requests(self) -> None:
        """쓰기 요청은 막고(요청차단), 헬스케어 목록 읽기 응답의 날짜는 2026 기준으로 옮긴다."""
        if self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            api = "taekwonworld" in q.url and q.resource_type in ("xhr", "fetch")
            if api and "/hc/select-body/" in q.url:
                res = r.fetch()
                r.fulfill(response=res, body=redate(res.text()), content_type="application/json")
                self.log.setdefault("faked", []).append("hc/select-body 날짜")
                return
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            if api and write and self.blocked(pg.url or "") and "read" not in q.url.lower():
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
                return
            r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def card(self, s, end, hot, first=False):
        pg = self.pg
        if not pg.url.startswith(INFO):
            pg.goto(INFO, wait_until="load")
            pg.wait_for_timeout(1200)
        h = self.box_of(pg.locator(f"#{hot}"))
        self.spot(self.rect(h["x"] - 8, h["y"] - 8, h["width"] + 16, h["height"] + 16), self.now(), end + 0.2, 0)
        self.glide(h["x"] + h["width"] * 0.5, h["y"] + h["height"] * 0.35, 0.9)
        if not first:
            for y in (0.35, 0.6, 0.85):
                self.glide(h["x"] + h["width"] * 0.3, h["y"] + h["height"] * y, max(0.6, self.dur[s.key] * 0.2))

    # ── 1단계: 측정기 연결하기 ──
    def do_D1(self, s, end):
        self.card(s, end, "hot-a", first=True)

    def do_D2(self, s, end):
        self.card(s, end, "hot-b")
        self.wait_until(end)
        self.pg.goto(HOME, wait_until="domcontentloaded")          # 문장 사이: 첫 화면(안내 창)으로 돌아가기
        self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
        self.sleep(0.6)

    def do_B1(self, s, end):                       # 첫 화면 알림 배너(가리키기만)
        b = self.holder_box("ACCUNIQ 체성분 분석기 이벤트", 600, 40)
        if not b:
            raise SceneError(s, "알림", "첫 화면 알림을 찾지 못했어요")
        self.spot(self.rect(262, b["y"] - 8, 1612, b["height"] + 16), self.now(), end + 0.2, 0)
        self.glide(b["x"] + 200, b["y"] + b["height"] / 2, 0.9)
        self.wait_until(end - 0.1)

    # ── 2단계: 측정결과 보기 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "헬스케어", "측정결과 조회", "/healthcare/list")
        self.pg.get_by_text("측정일시").first.wait_for(timeout=15000)
        self.sleep(0.4)

    def do_K1(self, s, end):                       # 목록 → 반·이름 찾기
        pg = self.pg
        head = self.leaf("측정일시")
        rows = self.box_of(pg.locator("text=2026-10-15").last)       # 날짜를 옮겨 보여 주므로 2026 기준
        if head:
            self.spot(self.rect(262, head["y"] - 22, 1630, rows["y"] + rows["height"] + 26 - (head["y"] - 22)),
                      self.now(), self.now() + max(1.8, self.dur[s.key] * 0.5), 0)
            self.glide(700, head["y"] + 80, 0.8)
            self.glide(700, rows["y"], max(0.8, self.dur[s.key] * 0.25))
        cls = self.box_of(pg.locator(".MuiSelect-select").first)
        q = self.box_of(pg.get_by_role("button", name="조회", exact=True).first)
        self.spot(self.union(cls, q, pad=8), self.now(), end + 0.2, 0)
        self.glide(cls["x"] + 80, cls["y"] + cls["height"] / 2, 0.7)
        self.sleep(max(0.4, self.dur[s.key] * 0.12))
        self.glide(q["x"] - 120, q["y"] + q["height"] / 2, 0.6)

    def do_K2(self, s, end):                       # 필터 단추 → 고르는 칸 → 닫기
        pg = self.pg
        f = {"x": 263, "y": 208, "width": 46, "height": 46}         # 날짜 칸 왼쪽 필터 단추(글자가 없어 자리로)
        s0 = self.now()
        self.go_click(f, 0.8)
        self.spot(f, s0, self.now() + 0.2, 8)
        pop = pg.locator(".MuiPopover-paper, .MuiModal-root [role=presentation] .MuiPaper-root").filter(has_text="적용하기").last
        pop.wait_for(timeout=8000)
        self.sleep(0.4)
        pb = self.box_of(pop)
        self.spot(pb, self.now(), end - 0.4, 4)
        self.glide(pb["x"] + 80, pb["y"] + 60, 0.6)
        self.glide(pb["x"] + 80, pb["y"] + pb["height"] - 120, max(0.8, self.dur[s.key] * 0.3))
        self.wait_until(end - 0.4)
        pg.keyboard.press("Escape")
        self.sleep(0.4)
        if pg.locator(".MuiPopover-paper").filter(has_text="적용하기").count():
            self.outside_close()

    def do_K3(self, s, end):                       # 아큐닉 대시보드(가리키기만, 바깥 사이트라 열지 않음)
        b = self.holder_box("ACCUNIQ 대시보드", 1000, 80)
        if not b:
            raise SceneError(s, "아큐닉 대시보드", "대시보드 띠를 찾지 못했어요")
        self.spot(b, self.now(), end + 0.2, 4)
        self.glide(b["x"] + 160, b["y"] + b["height"] / 2, 0.9)
        self.wait_until(end - 0.1)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)

    def do_M2(self, s, end):                       # 헬스케어 메뉴: 두 가지 → 키(신장) 기록 누르기
        self.phone(s, end, 2)
        h = self.box_of(self.pg.locator("#hot-2"))
        self.wait_until(end - 1.0)
        self.glide(h["x"] + h["width"] * 0.6, h["y"] + h["height"] * 0.22, 0.6)
        self.sleep(0.15)
        self.click()

    def do_M3(self, s, end): self.phone(s, end, 3)
    def do_M4(self, s, end): self.phone(s, end, 4)
    def do_M5(self, s, end): self.phone(s, end, 5)


maker.Recorder = Ep17Recorder


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

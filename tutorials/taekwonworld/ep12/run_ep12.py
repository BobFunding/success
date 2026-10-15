"""12편(공지) 만들기: 10편 녹화기(안내 창 닫기·메뉴 이동·글자 찾기) + 이 편만의 동작.
사용: python run_ep12.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 데모 도장. 사용자 승인으로 'A반 오후 2시'(class=1)에 미리 올려 둔 시험 공지를 목록·상세에서 보여 준다(촬영 뒤 지움).
- 안전: 공지 화면의 쓰기 요청(등록·댓글·삭제)은 모두 막는다. 삭제 메뉴는 가리키기만 한다.
- 흐림: 댓글 단 사람 이름.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep10"))
sys.path.insert(0, str(HERE.parent / "ep8"))
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep10 as E10                                        # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

PHONE = (HERE / "phone" / "phone.html").as_uri()
TITLE = "[시험] 10월 승급심사 안내"                            # 미리 올려 둔 공지와 같은 제목
BODY = "10월 25일(토) 오전 10시에 승급심사가 있습니다.\n도복과 띠를 꼭 챙겨 주세요."
CLASS = "A반 오후 2시"

# 공지 상세: 댓글 단 사람 이름 흐림(사진 옆 2~10글자)
BLUR12 = r"""(() => {
  const run = () => {
    if (!/\/app\/notice/.test(location.pathname)) return;
    for (const m of document.querySelectorAll('.MuiModal-root')) {
      for (const e of m.querySelectorAll('div, span, p')) {
        if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
        const t = (e.innerText || '').trim();
        if (!/^[가-힣A-Za-z0-9 ]{2,14}(부|모|어머니|아버지|보호자)?$/.test(t) || /공지|댓글|태권월드|승급|반 /.test(t)) continue;
        for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
          if (p.querySelector('img[alt=Profile], img[src*="profile"], img[src*="student/img"], img[src*="parent"]')) { e.classList.add('__tm_blur'); break; }
      }
    }
  };
  setInterval(run, 120);
})()"""


class Ep12Recorder(E10.Ep10Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR12)
        super().scenario()

    # ── 1단계 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "앱", "공지", "/app/notice/list")
        self.pg.get_by_text("공지 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):                       # 공지 사용 가이드 → 닫기
        pg = self.pg
        guide = self.guide_box("공지 사용 가이드")
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        b = self.box_of(pg.get_by_text("닫기", exact=True).last)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.sleep(0.6)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    # ── 2단계 ──
    def form(self):
        return self.pg.locator(".MuiModal-root").filter(has_text="공지 작성").last

    def do_W1(self, s, end):
        pg = self.pg
        b = self.box_of(pg.locator("button:has-text('공지 작성')").first)
        s0 = self.now()
        self.spot(b, s0, end + 0.2, 8)
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.go_click(b, 0.8)
        pg.locator("input[name=title]").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_W2(self, s, end):                       # 반 고르기 → A반 오후 2시
        pg = self.pg
        sel = self.form().locator("input[name=class_arr]").locator("xpath=..").locator(".MuiSelect-select")
        b = self.box_of(sel)
        s0 = self.now()
        self.spot(self.rect(b["x"] - 10, b["y"] - 10, b["width"] + 20, b["height"] + 20), s0, s0 + 1.6, 0)
        self.go_click(b, 0.8)
        lst = pg.locator("[role=listbox]").first
        lst.wait_for(timeout=5000)
        self.sleep(0.3)
        self.spot(self.box_of(lst), self.now(), end - 0.2, 4)
        first = self.box_of(pg.locator("li[role=option]").first)
        self.glide(first["x"] + 60, first["y"] + first["height"] / 2, 0.5)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        opt = self.box_of(pg.locator("li[role=option]").filter(has_text=CLASS).first)
        self.go_click(opt, 0.5)
        self.sleep(0.3)
        if pg.locator("[role=listbox]").count():   # 여러 개 고르는 목록이면 바깥을 눌러 닫는다
            pg.keyboard.press("Escape")
            self.sleep(0.3)

    def do_W3(self, s, end):                       # 제목·내용
        pg = self.pg
        t = self.box_of(pg.locator("input[name=title]").first)
        c = self.box_of(pg.locator("textarea[name=contents]").first)
        s0 = self.now()
        self.spot(self.union(t, c, pad=12), s0, end + 0.2, 0)
        self.type_in("input[name=title]", TITLE, move=0.6, delay=0.06)
        self.sleep(0.2)
        self.type_in("textarea[name=contents]", BODY, move=0.5, delay=0.035)

    def do_W4(self, s, end):                       # 사진·동영상·문서 칸
        pg = self.pg
        a = self.box_of(self.form().get_by_text("사진 (0/10)").first)
        z = self.box_of(self.form().get_by_text("문서 (0/3)").first)
        band = self.rect(a["x"] - 14, a["y"] - 12, self.box_of(self.form().locator("input[name=title]"))["width"] + 30, z["y"] + z["height"] - a["y"] + 60)
        s0 = self.now()
        self.spot(band, s0, end + 0.2, 0)
        self.glide(a["x"] + 80, a["y"] + 10, 0.8)
        self.glide(z["x"] + 80, z["y"] + 10, max(1.2, self.dur[s.key] * 0.5))

    def do_W5(self, s, end):                       # 등록(막힘) → 창 닫기(뒤로)
        pg = self.pg
        loc = self.form().locator("button[type=submit]:has-text('등록')").first
        loc.scroll_into_view_if_needed(timeout=5000)          # 창 아래 끝에 있어 화면 밖일 수 있다
        self.sleep(0.3)
        btn = self.box_of(loc)
        s0 = self.now()
        self.glide(btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2, 0.9)
        self.spot(btn, s0 + 0.3, end + 0.2, 10)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.8)
        if self.mode == "dry" and not any("noticecreate" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", "등록 단추가 눌리지 않았어요")
        if self.form().count():                    # 등록이 막혀 창이 남으면 바깥을 살짝 눌러 닫는다(창 바로 옆)
            fb = self.box_of(self.form().locator(".MuiPaper-root, [role=dialog]").first) if self.form().locator(".MuiPaper-root, [role=dialog]").count() else None
            x = (fb["x"] + fb["width"] + 60) if fb else 1700
            self.glide(min(x, 1880), 540, 0.4); self.sleep(0.05); self.click()
            self.sleep(0.5)
            if self.form().count():
                pg.keyboard.press("Escape"); self.sleep(0.4)

    # ── 3단계 ──
    def do_V1(self, s, end):                       # 반 필터 → A반 오후 2시 → 목록
        pg = self.pg
        sel = pg.locator(".MuiSelect-select").filter(has_text="도장 공지").first
        b = self.box_of(sel)
        s0 = self.now()
        self.spot(self.rect(b["x"] - 10, b["y"] - 10, 760, b["height"] + 20), s0, s0 + 2.0, 0)
        self.go_click(b, 0.8)
        pg.locator("li[role=option]").filter(has_text=CLASS).first.wait_for(timeout=5000)
        self.sleep(0.3)
        self.go_click(self.box_of(pg.locator("li[role=option]").filter(has_text=CLASS).first), 0.5)
        pg.get_by_text(TITLE).first.wait_for(timeout=10000)
        self.sleep(0.5)
        item = self.holder_box(TITLE, 600, 60)
        if item:
            self.glide(item["x"] + 300, item["y"] + item["height"] / 2, 0.7)
            self.spot(item, self.now() - 0.2, end + 0.2, 6)

    def do_V2(self, s, end):                       # 공지 열기 → 댓글 자리
        pg = self.pg
        t = self.box_of(pg.get_by_text(TITLE).first)
        s0 = self.now()
        self.go_click(t, 0.7)
        pg.locator(".MuiModal-root input[name=contents]").wait_for(timeout=8000)
        self.sleep(0.5)
        m = self.holder_box("공지", 400, 400)
        cin = self.box_of(pg.locator(".MuiModal-root input[name=contents]").first)
        cm = pg.get_by_text("댓글 0").first if pg.get_by_text("댓글 0").count() else pg.locator(".MuiModal-root").get_by_text("댓글").first
        cb = self.box_of(cm)
        area = self.rect(cin["x"] - 20, cb["y"] - 14, cin["width"] + 80, cin["y"] + cin["height"] - cb["y"] + 28)
        if m:
            self.spot(m, self.now(), self.now() + 1.4, 4)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(cin["x"] + 120, cin["y"] + cin["height"] / 2, 0.7)
        self.spot(area, self.now() - 0.3, end + 0.2, 0)

    def dots_box(self):
        loc = self.pg.locator(".MuiModal-root button").filter(has=self.pg.locator("svg[data-testid=MoreVertRoundedIcon]")).last
        return loc.bounding_box() if loc.count() else None

    def do_V3(self, s, end):                       # 점 세 개 → 삭제(가리키기만) → 메뉴 닫기
        pg = self.pg
        d = self.dots_box()
        if not d:
            raise SceneError(s, "점 세 개", "공지 메뉴 단추를 찾지 못했어요")
        s0 = self.now()
        self.spot(d, s0, s0 + 1.6, 10)
        self.go_click(d, 0.8)
        self.sleep(0.5)
        dl = pg.locator(".MuiPopover-paper").get_by_text("삭제", exact=True).first
        if dl.count():
            db = self.box_of(dl)
            self.glide(db["x"] + db["width"] / 2, db["y"] + db["height"] / 2, 0.6)        # 가리키기만
            self.spot(db, self.now() - 0.3, end + 0.2, 8)
        self.wait_until(end - 0.1)
        pg.keyboard.press("Escape")
        self.sleep(0.3)

    # ── 학부모님 휴대폰 ──
    def phone(self, s, end, n, tap=False):
        pg = self.pg
        if not pg.url.startswith(PHONE):
            pg.goto(f"{PHONE}#{n}", wait_until="load")
            pg.wait_for_timeout(1200)
        pg.evaluate(f"show({n})")
        self.sleep(0.5)
        h = self.box_of(pg.locator(f"#hot-{n}"))
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.15))
        self.glide(h["x"] + h["width"] * 0.6, h["y"] + h["height"] * 0.55, 0.8)
        if tap:
            self.sleep(0.2)
            self.click()
        self.spot(self.rect(h["x"] - 6, h["y"] - 6, h["width"] + 12, h["height"] + 12), s0, end + 0.2, 0)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)
    def do_M2(self, s, end): self.phone(s, end, 2)


maker.Recorder = Ep12Recorder


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
        dur = {k: v[2] for k, v in maker.narrate(sc, work).items()}
        print(maker.rehearse(sc, work, dur))
    else:
        print(maker.make(sc, work, fast="--fast" in sys.argv))

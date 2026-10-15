"""13편(알림장) 만들기: 12편 녹화기(안내 창 닫기·메뉴 이동·창 닫기 nozoom·휴대폰) + 이 편만의 동작.
사용: python run_ep13.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 데모 도장에 이미 보낸 알림장을 목록·상세에서 보여 준다(새로 보내지 않음).
- 안전: 알림장 화면의 쓰기 요청(등록·댓글·삭제)은 모두 막는다. 삭제 메뉴는 가리키기만 한다.
- 흐림: 수련생 이름(목록·상세·수련생 선택 창).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep12"))
import run_ep12 as E12                                        # noqa: E402
from run_ep12 import maker, S, SceneError                     # noqa: E402

E12.PHONE = (HERE / "phone" / "phone.html").as_uri()          # 12편 phone() 이 이 편 휴대폰 화면을 연다
BODY = "오늘 수업에서 발차기를 아주 잘했어요!\n집에서도 많이 칭찬해 주세요."
PICK = ["김태풍", "김테스트"]                                  # 고르는 수련생(이름은 흐림)

# 알림장 화면: 사진(아바타) 옆 2~4글자 이름 흐림. 메뉴·버튼 글자는 뺀다
BLUR13 = r"""(() => {
  const skip = /알림장|댓글|보낸|받은|전체|수련생|선택|내용|사진|등록|조회|초기화|공지|일정|반$/;
  const run = () => {
    if (!/\/app\/note/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!/^[가-힣]{2,4}$/.test(t) || skip.test(t)) continue;
      if (e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, i = 0; p && i < 6; p = p.parentElement, i++)
        if (p.querySelector('img, input[type=checkbox]')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 120);
})()"""


class Ep13Recorder(E12.Ep12Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR13)
        super().scenario()

    def modal(self, title):
        return self.pg.locator(".MuiModal-root").filter(has_text=title).last

    # ── 1단계 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "앱", "알림장", "/app/note/list")
        self.pg.get_by_text("알림장 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):                       # 알림장 사용 가이드 → 닫기
        pg = self.pg
        guide = self.guide_box("알림장 사용 가이드")
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        b = self.box_of(pg.get_by_text("닫기", exact=True).last)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.nozoom()
        self.sleep(0.6)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    # ── 2단계 ──
    def do_W1(self, s, end):
        pg = self.pg
        b = self.box_of(pg.locator("button:has-text('알림장 작성')").first)
        self.spot(b, self.now(), end + 0.2, 8)
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.go_click(b, 0.8)
        pg.locator("textarea[name=note_contents]").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_W2(self, s, end):                       # 수련생 선택 → 고르는 창
        pg = self.pg
        b = self.box_of(self.modal("알림장 작성").locator("button").filter(has_text="수련생 선택").first)
        self.spot(b, self.now(), end + 0.2, 8)
        self.sleep(max(0.4, self.dur[s.key] * 0.45))
        self.go_click(b, 0.7)
        self.modal("수련생 선택").locator("input[type=checkbox]").nth(1).wait_for(timeout=8000)
        self.sleep(0.4)

    def row_check(self, name):
        m = self.modal("수련생 선택")
        row = m.locator("tr, li, div").filter(has=self.pg.get_by_text(name, exact=True)).filter(has=self.pg.locator("input[type=checkbox]")).last
        return self.box_of(row.locator("input[type=checkbox]").first), self.box_of(row)

    def do_W3(self, s, end):                       # 두 명 체크
        c1, r1 = self.row_check(PICK[0])
        c2, r2 = self.row_check(PICK[1])
        self.spot(self.union(r1, r2, pad=4), self.now(), end + 0.2, 0)
        self.sleep(0.3)
        self.go_click(c1, 0.7)
        self.sleep(max(0.5, self.dur[s.key] * 0.25))
        self.go_click(c2, 0.5)
        self.sleep(0.3)

    def do_W4(self, s, end):                       # 선택
        pg = self.pg
        b = self.box_of(self.modal("수련생 선택").get_by_text("선택", exact=True).first)
        self.spot(b, self.now(), end + 0.2, 8)
        self.sleep(max(0.4, self.dur[s.key] * 0.4))
        self.go_click(b, 0.7)
        pg.get_by_text("선택 초기화").first.wait_for(timeout=8000)
        self.sleep(0.4)

    def do_W5(self, s, end):                       # 고른 수련생 + 선택 초기화(가리키기만)
        m = self.modal("알림장 작성")
        who = self.box_of(m.get_by_text("수련생 (2명)").first) if m.get_by_text("수련생 (2명)").count() else None
        r = self.box_of(m.get_by_text("선택 초기화").first)
        if who:
            self.spot(self.rect(who["x"] - 10, who["y"] - 8, r["x"] + r["width"] - who["x"] + 20, r["y"] + r["height"] - who["y"] + 16),
                      self.now(), self.now() + 1.6, 0)
        self.sleep(max(0.6, self.dur[s.key] * 0.35))
        self.glide(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2, 0.7)
        self.spot(r, self.now() - 0.3, end + 0.2, 8)

    def do_W6(self, s, end):                       # 내용
        c = self.box_of(self.pg.locator("textarea[name=note_contents]").first)
        self.spot(c, self.now(), end + 0.2, 10)
        self.type_in("textarea[name=note_contents]", BODY, move=0.6, delay=0.05)

    def do_W7(self, s, end):                       # 사진 칸 → 등록(막힘) → 창 닫기
        pg = self.pg
        m = self.modal("알림장 작성")
        ph = self.box_of(m.locator("button").filter(has_text="사진 추가").first)
        self.spot(ph, self.now(), self.now() + 1.8, 8)
        self.glide(ph["x"] + ph["width"] / 2, ph["y"] + ph["height"] / 2, 0.7)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        loc = m.locator("button").filter(has_text="등록").last
        loc.scroll_into_view_if_needed(timeout=5000)
        btn = self.box_of(loc)
        self.glide(btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2, 0.8)
        self.spot(btn, self.now() - 0.5, end + 0.2, 10)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.8)
        if self.mode == "dry" and not any("note" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", "등록 단추가 눌리지 않았어요")
        for _ in range(3):                         # 막혀 창이 남으면 제목 옆 뒤로(←)로 닫는다
            f = self.modal("알림장 작성")
            if not f.count() or not f.is_visible():
                break
            back = f.locator("button.MuiIconButton-root").first.bounding_box(timeout=3000)
            if back:
                self.glide(back["x"] + back["width"] / 2, back["y"] + back["height"] / 2, 0.4); self.click(); self.nozoom()
            else:
                pg.keyboard.press("Escape")
            self.sleep(0.6)

    # ── 3단계 ──
    def first_row(self):                           # 목록 첫 줄(보낸 알림장 표시 기준 한 줄 높이 121px)
        b = self.box_of(self.pg.get_by_text("보낸 알림장", exact=True).first)
        return self.rect(b["x"] - 105, b["y"] - 18, 1628, 121)

    def do_V1(self, s, end):                       # 목록 + 반·연·월 고르기
        pg = self.pg
        sels = pg.locator(".MuiSelect-select")
        a, c = self.box_of(sels.nth(0)), self.box_of(sels.nth(2))
        row = self.first_row()
        self.spot(self.rect(row["x"], row["y"], row["width"], row["height"] * 3), self.now(), self.now() + max(1.6, self.dur[s.key] * 0.4), 0)
        self.glide(row["x"] + 400, row["y"] + row["height"] / 2, 0.8)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        self.spot(self.union(a, c, pad=8), self.now(), end + 0.2, 0)
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2, 0.8)

    def do_V2(self, s, end):                       # 받은/보낸 고르기(열어서 보여 주기만)
        pg = self.pg
        sel = pg.locator(".MuiSelect-select").filter(has_text="알림장").first
        b = self.box_of(sel)
        self.spot(b, self.now(), self.now() + 1.4, 8)
        self.go_click(b, 0.8)
        lst = pg.locator("[role=listbox]").first
        lst.wait_for(timeout=5000)
        self.sleep(0.3)
        self.spot(self.union(b, self.box_of(lst), pad=6), self.now(), end + 0.2, 0)
        o = self.box_of(pg.locator("li[role=option]").filter(has_text="받은 알림장").last)
        self.glide(o["x"] + 60, o["y"] + o["height"] / 2, 0.6)
        self.wait_until(end - 0.2)
        pg.keyboard.press("Escape")
        self.sleep(0.4)

    def do_V3(self, s, end):                       # 알림장 열기 → 댓글 자리
        pg = self.pg
        t = self.first_row()
        self.go_click(self.rect(t["x"] + 330, t["y"] + 84, 20, 16), 0.7)          # 첫 줄 내용 글자
        cin = pg.get_by_placeholder("댓글 작성").first
        cin.wait_for(timeout=8000)
        self.sleep(0.5)
        m = self.box_of(pg.locator(".MuiModal-root").last.locator(".MuiPaper-root, [role=dialog]").first) if pg.locator(".MuiModal-root .MuiPaper-root, .MuiModal-root [role=dialog]").count() else None
        cb = self.box_of(cin)
        cm = self.box_of(pg.locator(".MuiModal-root").last.get_by_text("댓글이 없습니다").first) if pg.locator(".MuiModal-root").last.get_by_text("댓글이 없습니다").count() else cb
        if m:
            self.spot(m, self.now(), self.now() + 1.4, 4)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(cb["x"] + 120, cb["y"] + cb["height"] / 2, 0.7)
        self.spot(self.union(cm, cb, pad=10), self.now() - 0.3, end + 0.2, 0)

    def do_V4(self, s, end):                       # 점 세 개 → 삭제(가리키기만) → 메뉴 닫기
        E12.Ep12Recorder.do_V3(self, s, end)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)
    def do_M2(self, s, end): self.phone(s, end, 2)


maker.Recorder = Ep13Recorder


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

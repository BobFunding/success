"""6편(수련생 등록) 만들기: 3편 녹화기(로그인·도장 선택·안내 창·쓰기 차단) + 이 편만의 동작.
사용: python run_ep6.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 한 명씩: 신규 수련생 등록에 예시 값(가짜)을 적고 [등록](수련생 쓰기 요청 차단 — 실제로 생기지 않음).
  출석번호 중복확인은 읽기(GET)라 그대로 둔다.
- 여러 명: 일괄 등록 → [일괄 등록 양식](내려받기 대신) 실제 양식을 본뜬 엑셀 화면(excel_mock.html)에서 칸 적기
  → 다시 일괄 등록 화면의 메일 주소.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep3 as E3                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

MOCK = (HERE / "excel_mock.html").as_uri()
LUMP = "https://taekwonworld.net/manage/student/regist/lump"
ATTEND = "0815"            # 출석번호 예시(데모 도장에 없는 번호)
# 예시 수련생(가짜): 성, 이름, 성별(0 남), 생년월일, 반, 급수, 급/품/단, 보호자, 청구서 번호, 수강료, 납부일, 도장 등록일
KID = dict(last="김", first="태권", sex="0", dob="20180315", cls="A반 오후 2시", lv="6", lvk="급",
           rep="김엄마", bill="01098765432", fee="150000", due="10", reg="20261001")


class Ep6Recorder(E3.Ep3Recorder):
    def block_requests(self) -> None:
        """수련생 화면의 쓰기(POST/PUT/PATCH/DELETE)만 막는다. 중복확인 같은 읽기(GET)는 통과."""
        if not self.sc.block_list or self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            api = "taekwonworld" in q.url and "collect" not in q.url
            if self.blocked(pg.url or "") and write and api and "read" not in q.url.lower():
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
            else:
                r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def scenario(self) -> None:
        self._dialogs = []
        self.pg.on("dialog", lambda d: self._dialogs.append(d.message))
        super().scenario()

    def blocked(self, url: str) -> bool:
        return "/manage/student" in url

    def run_scene(self, s, last):
        if s.key == "P1":
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super(E3.Ep3Recorder, self).run_scene(s, last)

    # ── 공통 ──
    def go_click(self, b, move=0.6):
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, move)
        self.sleep(0.1)
        self.click()

    def box_of(self, loc):
        b = loc.bounding_box()
        if not b:
            raise SceneError(self.scene, self.scene.label, "누를 곳을 찾지 못했어요")
        return b

    def mui_pick(self, select_loc, text, move=0.5):
        """MUI 선택 상자를 열고 글자가 text 로 시작하는 항목을 고른다(목록이 길면 그 항목까지 굴려서)."""
        self.go_click(self.box_of(select_loc), move)
        self.sleep(0.35)
        opt = self.pg.locator("li[role=option]").filter(has_text=text).first
        opt.scroll_into_view_if_needed(timeout=5000)
        self.sleep(0.2)
        self.go_click(self.box_of(opt), 0.4)
        self.sleep(0.25)

    def field_select(self, name):
        return self.pg.locator(f"input[name={name}]").first.locator("xpath=..").locator(".MuiSelect-select")

    def union(self, *bs, pad=8):
        x0 = min(b["x"] for b in bs); y0 = min(b["y"] for b in bs)
        x1 = max(b["x"] + b["width"] for b in bs); y1 = max(b["y"] + b["height"] for b in bs)
        return self.rect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)

    def guide_box(self, title):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>400 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""", title)

    def card(self, title):
        """등록 방법 카드(제목 글자를 품은 상자)."""
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<6&&c;i++){ const r=c.getBoundingClientRect(); if (r.height>120 && r.width>200) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; }
            const r=t.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", title)

    # ── 1단계 ──
    def do_P1(self, s, end):
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("수련생 등록")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/manage/student/regist", timeout=20000)
        self.pg.get_by_text("수련생 일괄 등록").first.wait_for(timeout=20000)
        self.sleep(0.4)

    def do_P2(self, s, end):                       # 신규·일괄 두 카드
        a, b = self.card("신규 수련생 등록"), self.card("수련생 일괄 등록")
        s0 = self.now()
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] + 30, 0.8)
        self.spot(self.union(a, b, pad=10), s0, end + 0.2, 0)
        self.sleep(max(0.5, self.dur[s.key] * 0.45))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] + 30, 0.8)

    # ── 2단계 ──
    def do_N1(self, s, end):
        a = self.card("신규 수련생 등록")
        btn = self.pg.get_by_text("등록하기", exact=True).nth(0)
        s0 = self.now()
        self.spot(a, s0, end + 0.2, 8)
        self.sleep(max(0.4, self.dur[s.key] * 0.4))
        self.go_click(self.box_of(btn), 0.8)
        self.pg.wait_for_url("**/regist/new", timeout=20000)
        self.pg.get_by_text("수련생 등록 사용 가이드").wait_for(timeout=20000)
        self.sleep(0.4)

    def do_N2(self, s, end):                       # 사용 가이드(사진 안내) → 닫기
        g = self.guide_box("수련생 등록 사용 가이드")
        close = self.box_of(self.pg.get_by_text("닫기", exact=True).last)
        s0 = self.now()
        if g:
            self.spot(g, s0, s0 + max(1.5, self.dur[s.key] * 0.6), 6)
        self.sleep(max(0.8, self.dur[s.key] * 0.55))
        self.glide(close["x"] + close["width"] / 2, close["y"] + close["height"] / 2, 0.7)
        self.spot(self.rect(close["x"] - 8, close["y"] - 6, close["width"] + 16, close["height"] + 12), self.now() - 0.7, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.get_by_text("수련생 등록 사용 가이드").wait_for(state="hidden", timeout=8000)

    def do_F1(self, s, end):                       # 이름·생년월일·성별
        pg = self.pg
        last, first = pg.locator("input[name=LAST_NAME]"), pg.locator("input[name=FIRST_NAME]")
        sex = self.field_select("SEX_CODE")
        s0 = self.now()
        u = self.union(self.box_of(last), self.box_of(sex))
        self.spot(self.rect(u["x"] - 140, u["y"], u["width"] + 140, u["height"]), s0, end + 0.3, 0)
        x, y, b = self.center("input[name=LAST_NAME]", "이름")
        self.glide(x, y, 0.6)
        self.typ("input[name=LAST_NAME]", KID["last"], 0.12)
        self.typ("input[name=FIRST_NAME]", KID["first"], 0.12)
        dob = pg.locator("input[name=DOB]")
        for k, t in enumerate((KID["dob"][:4] + "년", str(int(KID["dob"][4:6])) + "월", str(int(KID["dob"][6:])) + "일")):
            self.mui_pick(dob.nth(k).locator("xpath=..").locator(".MuiSelect-select"), t, 0.4)
        self.mui_pick(sex, "남자" if KID["sex"] == "0" else "여자", 0.4)

    def do_F2(self, s, end):                       # 급/품/단: 우리 도장 급띠 목록에서
        sel = self.field_select("STUDENT_LEVEL")
        s0 = self.now()
        self.spot(self.rect(*(lambda b: (b["x"] - 140, b["y"] - 6, b["width"] + 150, b["height"] + 12))(self.box_of(sel))), s0, s0 + 1.2, 0)
        self.go_click(self.box_of(sel), 0.6)
        self.sleep(0.4)
        lst = self.pg.locator("ul[role=listbox]").first
        lb = lst.bounding_box()
        if lb:
            self.spot(self.rect(lb["x"] - 6, lb["y"] - 6, lb["width"] + 12, min(lb["height"], 520) + 12), self.now() - 0.2, end + 0.2, 0)
        opt = self.pg.locator("li[role=option]").filter(has_text=f"{KID['lv']}{KID['lvk']}").first
        self.glide(self.box_of(opt)["x"] + 60, self.box_of(opt)["y"] + 14, 0.9)
        self.wait_until(max(self.now() + 0.6, end - 0.6))
        opt.scroll_into_view_if_needed(timeout=5000)
        self.go_click(self.box_of(opt), 0.3)
        self.sleep(0.2)

    def do_F3(self, s, end):                       # 반 + 출석번호 + 중복확인
        pg = self.pg
        cls = self.field_select("CLASS_ID")
        s0 = self.now()
        a = self.box_of(cls)
        dup = self.box_of(pg.get_by_text("중복확인").first)
        self.spot(self.rect(a["x"] - 140, a["y"] - 6, dup["x"] + dup["width"] - a["x"] + 150, dup["y"] + dup["height"] - a["y"] + 12), s0, end + 0.3, 0)
        self.mui_pick(cls, KID["cls"], 0.6)
        self.typ("input[name=ATTEND_NUM]", ATTEND, 0.12)
        n0 = len(self._dialogs)
        self.go_click(dup, 0.5)
        self.sleep(0.8)
        if self.mode == "dry" and any("이미" in m for m in self._dialogs[n0:]):
            raise SceneError(s, "출석번호", f"출석번호 {ATTEND} 이(가) 이미 있어요. run_ep6.py 의 ATTEND 를 바꿔 주세요")

    def do_F4(self, s, end):                       # 보호자·청구서 번호·수련비·납부일
        pg = self.pg
        s0 = self.now()
        top = self.box_of(pg.locator("input[name=REP_PHONE_NUMBER]"))
        bot = self.box_of(pg.locator("input[name=DUE_DATE]"))
        self.spot(self.rect(top["x"] - 230, top["y"] - 8, bot["x"] + bot["width"] - top["x"] + 240, bot["y"] + bot["height"] - top["y"] + 16), s0, end + 0.3, 0)
        x, y, _ = self.center("input[name=REP_PHONE_NUMBER]", "보호자")
        self.glide(x, y, 0.6)
        self.typ("input[name=REP_PHONE_NUMBER]", KID["bill"], 0.05)
        self.typ("input[name=REP_REL]", "엄마", 0.1)
        self.typ("input[name=REP_NAME]", KID["rep"], 0.1)
        self.mui_pick(self.field_select("BILLING_TARGET_ROLE"), "보호자1", 0.5)
        self.typ("input[name=PAYING_AMOUNT]", KID["fee"], 0.06)
        self.typ("input[name=DUE_DATE]", KID["due"], 0.1)

    def do_F5(self, s, end):                       # 등록(차단)
        btn = self.pg.locator("button:text-is('등록')").first
        b = self.box_of(btn)
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.go_click(b, 0.9)
        self.spot(b, s0, end + 0.2, 8)
        try:
            self.pg.get_by_text("태권월드 초대장 보내기").first.wait_for(timeout=8000)
        except Exception:
            raise SceneError(s, "등록", f"등록 확인 창이 뜨지 않았어요(빈 칸이 있는지 확인) {self._dialogs[-2:]}") from None
        self.sleep(0.4)

    def do_F6(self, s, end):                       # 등록 확인 창: 초대장 보내기 체크 → 등록(차단)
        pg = self.pg
        dlg = self.guide_box("초대장 문자sms 예시") or self.pg.evaluate("""() => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && /수련생을 등록합니다/.test(e.innerText||''));
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>250 && r.height>350) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""")
        chk = self.box_of(pg.get_by_text("태권월드 초대장 보내기").first)
        modal = pg.locator(".MuiModal-root").filter(has_text="태권월드 초대장 보내기").last
        ok = self.box_of(modal.locator("button:text-is('등록')").first)
        s0 = self.now()
        if dlg:
            self.spot(dlg, s0, s0 + max(1.6, self.dur[s.key] * 0.35), 4)
        self.sleep(max(1.2, self.dur[s.key] * 0.3))
        self.glide(chk["x"] - 14, chk["y"] + chk["height"] / 2, 0.7)
        self.spot(self.rect(chk["x"] - 34, chk["y"] - 8, chk["width"] + 44, chk["height"] + 16), self.now() - 0.3, self.now() + 1.8, 0)
        self.wait_until(max(self.now() + 1.4, end - 1.3))
        self.go_click(ok, 0.7)
        self.spot(ok, self.now() - 0.7, end + 0.2, 8)
        self.sleep(0.8)
        if self.mode == "dry" and not any("taekwonworld" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", f"등록 요청이 막히지 않았어요 {self._dialogs[-2:]}")

    # ── 3단계 ──
    def do_L1(self, s, end):                       # 수련생 등록 → 일괄 등록
        pg = self.pg
        # 등록(차단) 뒤 남은 확인 창은 [취소]로 닫는다
        m = pg.locator(".MuiModal-root").filter(has_text="태권월드 초대장 보내기")
        if m.count():
            cancel = m.last.locator("button:text-is('취소')").first
            if cancel.count():
                self.go_click(self.box_of(cancel), 0.5)
            else:
                pg.keyboard.press("Escape")
            m.last.wait_for(state="detached", timeout=5000)
            self.sleep(0.3)
        reg = self.side("수련생 등록")
        s0 = self.now()
        if reg:
            self.spot(reg, s0, s0 + 1.4, 6)
            self.go_click(reg, 0.8)
        else:
            pg.goto("https://taekwonworld.net/manage/student/regist", wait_until="domcontentloaded")
        pg.get_by_text("수련생 일괄 등록").first.wait_for(timeout=20000)
        self.sleep(0.5)
        b = self.card("수련생 일괄 등록")
        btn = pg.get_by_text("등록하기", exact=True).nth(1)
        self.spot(b, self.now(), end + 0.2, 8)
        self.go_click(self.box_of(btn), 0.8)
        pg.wait_for_url("**/regist/lump", timeout=20000)
        pg.get_by_text("일괄 등록 양식").first.wait_for(timeout=20000)
        self.sleep(0.3)

    def do_L2(self, s, end):                       # 양식 내려받기 → 엑셀 화면
        pg = self.pg
        link = pg.locator("a:has-text('일괄 등록 양식')").first
        b = self.box_of(link)
        s0 = self.now()
        self.spot(b, s0, end + 0.2, 8)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.wait_until(end - 0.5)
        self.click()                               # 새 창/내려받기는 녹화에 안 보이므로 바로 엑셀 화면으로
        self.sleep(0.3)
        for p in pg.context.pages[1:]:
            p.close()
        pg.goto(MOCK, wait_until="load")
        pg.wait_for_timeout(1200)                  # 글꼴
        self.sleep(0.3)

    def cell(self, c):
        return self.pg.locator(f"td[data-c='{c}']").first

    def do_X1(self, s, end):                       # 필수 안내 + 빨간 제목 줄 + 예시 줄
        a1, r3 = self.box_of(self.cell("A1")), self.box_of(self.pg.locator("tr.r3"))
        r2 = self.box_of(self.pg.locator("tr.r2"))
        s0 = self.now()
        self.glide(a1["x"] + a1["width"] / 2, a1["y"] + a1["height"] / 2, 0.8)
        self.spot(self.rect(a1["x"] - 4, a1["y"] - 4, a1["width"] + 8, a1["height"] + 8), s0, s0 + 2.0, 0)
        self.sleep(1.6)
        self.glide(r3["x"] + 300, r3["y"] + r3["height"] / 2, 0.8)
        self.spot(self.rect(r3["x"], r3["y"] - 2, min(r3["width"], 1900), r3["height"] + 4), s0 + 2.0, s0 + max(3.4, self.dur[s.key] * 0.6), 0)
        self.wait_until(s0 + max(3.4, self.dur[s.key] * 0.6) - 0.4)
        self.glide(r2["x"] + 300, r2["y"] + r2["height"] / 2, 0.6)
        self.spot(self.rect(r2["x"], r2["y"] - 2, min(r2["width"], 1900), r2["height"] + 4), self.now() - 0.4, end + 0.2, 0)

    def type_cell(self, c, text, delay=0.07):
        x, y, b = self.center(f"#{c}", c)
        self.glide(x, y, 0.35)
        self.typ(f"#{c}", text, delay)
        self.sleep(0.1)

    def do_X2(self, s, end):                       # B~F: 성·이름·성별·생년월일·소속반
        s0 = self.now()
        u = self.union(self.box_of(self.cell("B3")), self.box_of(self.pg.locator("#F4")), pad=2)
        self.spot(u, s0, end + 0.3, 0)
        for c, v in (("B4", KID["last"]), ("C4", KID["first"]), ("D4", KID["sex"]), ("E4", KID["dob"]), ("F4", KID["cls"])):
            self.type_cell(c, v)
        if self.mode == "dry" and self.pg.locator("#F4").input_value() != KID["cls"]:
            raise SceneError(s, "소속반", "엑셀 화면에 소속반이 들어가지 않았어요")

    def do_X3(self, s, end):                       # 급/품/단: 숫자 + 목록에서 급
        pg = self.pg
        s0 = self.now()
        u = self.union(self.box_of(self.cell("G1")), self.box_of(pg.locator("#H4")), pad=2)
        self.spot(self.rect(u["x"], u["y"], u["width"], u["height"] + 110), s0, end + 0.3, 0)
        self.type_cell("G4", KID["lv"], 0.1)
        x, y, b = self.center("#H4", "H4")
        self.glide(x, y, 0.4)
        self.click()
        self.sleep(0.3)
        dd = self.box_of(pg.locator("td.sel .dd"))
        self.go_click(dd, 0.35)
        self.sleep(0.4)
        it = self.box_of(pg.locator("#lst div", has_text=KID["lvk"]).first)
        self.go_click(it, 0.4)
        self.sleep(0.3)
        if self.mode == "dry" and pg.locator("#H4").input_value() != KID["lvk"]:
            raise SceneError(s, "급/품/단", "목록에서 고른 값이 들어가지 않았어요")

    def do_X4(self, s, end):                       # J·K·L·M·N
        s0 = self.now()
        u = self.union(self.box_of(self.cell("J3")), self.box_of(self.pg.locator("#N4")), pad=2)
        self.spot(u, s0, end + 0.3, 0)
        for c, v in (("J4", KID["rep"]), ("K4", KID["bill"]), ("L4", KID["fee"]), ("M4", KID["due"]), ("N4", KID["reg"])):
            self.type_cell(c, v, 0.05)

    def do_X5(self, s, end):                       # 다시 일괄 등록 화면: 메일 주소
        pg = self.pg
        pg.goto(LUMP, wait_until="domcontentloaded")
        pg.get_by_text("tkw@aivill.co.kr").first.wait_for(timeout=20000)
        self.sleep(0.4)
        mail = self.box_of(pg.get_by_text("tkw@aivill.co.kr").first)
        note = self.box_of(pg.get_by_text("작성하신 일괄 등록 양식과").first)
        s0 = self.now()
        self.glide(mail["x"] + mail["width"] + 30, mail["y"] + mail["height"] / 2, 0.8)
        self.spot(self.union(mail, note, pad=10), s0, end + 0.2, 0)


maker.Recorder = Ep6Recorder


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

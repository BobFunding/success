"""14편(일정) 만들기: 12편 녹화기(안내 창 닫기·메뉴 이동·창 닫기 nozoom·휴대폰) + 이 편만의 동작.
사용: python run_ep14.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 데모 도장 10월 달력이 비어 있어, 녹화 브라우저 안에서만 예시 일정 3개를 읽기 응답(schedulereadbymonth)에 보탠다.
  서버에는 아무것도 저장하지 않는다(9편 출결과 같은 방식).
- 안전: 일정 화면의 쓰기 요청(등록·저장·삭제)은 모두 막는다. 저장·삭제는 가리키기만 한다.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep12"))
import run_ep12 as E12                                        # noqa: E402
from run_ep12 import maker, S, SceneError                     # noqa: E402

E12.PHONE = (HERE / "phone" / "phone.html").as_uri()          # 12편 phone() 이 이 편 휴대폰 화면을 연다
DOJANG = 2                                                    # 데모 도장(태권월드 태권도장)
FAKE = [                                                      # 예시 일정(녹화 브라우저 안에서만 보임)
    {"CATEGORY": "심사", "TITLE": "10월 승급심사", "CONTENTS": "오전 10시, 도복과 띠를 꼭 챙겨 주세요.", "START_DATE": "20261025", "END_DATE": "20261025"},
    {"CATEGORY": "수련", "TITLE": "가을 야외 수련", "CONTENTS": "도장 앞 공원에서 모여요. 물과 간식을 챙겨 주세요.", "START_DATE": "20261017", "END_DATE": "20261018"},
    {"CATEGORY": "기타", "TITLE": "할로윈 파티", "CONTENTS": "재미있는 옷을 입고 와도 좋아요.", "START_DATE": "20261031", "END_DATE": "20261031"},
]
NEW_DAY = "29"                                                # 새 일정 날짜(10월 29일)
NEW_CAT = "교육"
NEW_TITLE = "학부모 공개 수업"
NEW_BODY = "오후 4시, 아이들이 수련하는 모습을 보러 오세요."


class Ep14Recorder(E12.Ep12Recorder):
    def block_requests(self) -> None:
        """쓰기 요청은 막고(요청차단), 10월 일정 읽기 응답에는 예시 일정을 보탠다."""
        if self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            api = "taekwonworld" in q.url and q.resource_type in ("xhr", "fetch")
            if api and "schedulereadbymonth" in q.url:
                try:
                    body = json.loads(q.post_data or "{}")
                except Exception:
                    body = {}
                if body.get("dojang_id") == DOJANG and str(body.get("year")) == "2026" and str(body.get("month")) == "10":
                    res = r.fetch()
                    d = res.json()
                    d["schedule_info"] = (d.get("schedule_info") or []) + [
                        dict(f, COUNTRY_CODE="0082", DOJANG_ID=DOJANG, SCHEDULE_ID=9000 + i,
                             CREATEDATE="2026-10-15T09:00:00.000Z", UPDATEDATE="2026-10-15T09:00:00.000Z") for i, f in enumerate(FAKE)]
                    self.log.setdefault("faked", []).append("schedulereadbymonth")
                    r.fulfill(response=res, body=json.dumps(d, ensure_ascii=False), content_type="application/json")
                    return
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            if api and write and self.blocked(pg.url or "") and "read" not in q.url.lower():
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
                return
            r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def modal(self, title):
        return self.pg.locator(".MuiModal-root").filter(has_text=title).last

    def day_cell(self, day):
        """큰 달력의 날짜 칸(숫자 글자 기준, 칸 크기 114×108)."""
        b = self.pg.evaluate("""(d) => { const t=[...document.querySelectorAll('div')].find(e=>{ if (e.childElementCount || e.innerText!==d) return false;
                 const r=e.getBoundingClientRect(); if (r.width<=0 || r.x<240 || r.x>1070 || r.y<200) return false;
                 const top=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2); return top && (top===e || e.contains(top)); });
              if (!t) return null; const r=t.getBoundingClientRect(); return {x:r.x, y:r.y, width:r.width, height:r.height}; }""", day)
        if not b:
            raise SceneError(self.scene, f"{day}일", "달력에서 날짜를 찾지 못했어요")
        return self.rect(b["x"] - 12, b["y"] - 12, 114, 108)

    def right_item(self, title):
        """오른쪽 '그날 일정' 칸의 일정 제목 상자(달력 칸 안 같은 글자는 뺀다)."""
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>!e.childElementCount && (e.innerText||'').trim()===w && e.getBoundingClientRect().x>1083);
            if (!t) return null; const r=t.getBoundingClientRect(); return {x:r.x, y:r.y, width:r.width, height:r.height}; }""", title)

    def pick_day(self, day, move=0.6):
        loc = self.pg.locator(f".react-datepicker__day--0{int(day):02d}:not(.react-datepicker__day--outside-month)").first
        loc.wait_for(timeout=5000)
        b = self.box_of(loc)
        self.go_click(b, move)
        self.sleep(0.4)

    # ── 1단계 ──
    def do_P2(self, s, end):
        self.menu_go(s, end, "앱", "일정", "/app/schedule/list")
        self.pg.get_by_text("일정 사용 가이드").first.wait_for(timeout=15000)

    def do_P3(self, s, end):                       # 일정 사용 가이드 → 닫기
        pg = self.pg
        guide = self.guide_box("일정 사용 가이드")
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

    def do_P4(self, s, end):                       # 달력 → 25일 누르기 → 오른쪽 그날 일정
        pg = self.pg
        self.spot(self.rect(262, 165, 800, 700), self.now(), self.now() + max(1.4, self.dur[s.key] * 0.35), 0)
        self.sleep(max(0.8, self.dur[s.key] * 0.3))
        c = self.day_cell("25")
        self.go_click(self.rect(c["x"] + 30, c["y"] + 10, 30, 20), 0.8)
        pg.get_by_text("2026년 10월 25일").first.wait_for(timeout=5000)
        self.sleep(0.3)
        right = self.rect(1083, 165, 808, 700)
        self.spot(right, self.now(), end + 0.2, 0)
        item = self.right_item("10월 승급심사")
        if item:
            self.glide(item["x"] + 120, item["y"] + item["height"] / 2, 0.7)

    # ── 2단계 ──
    def do_A1(self, s, end):
        pg = self.pg
        b = self.box_of(pg.locator("button:has-text('일정 추가')").first)
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.go_click(b, 0.8)
        self.spot(b, s0, self.now() + 0.2, 8)
        pg.locator("input[name=TITLE]").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_A2(self, s, end):                       # 시작 날짜 → 29일
        pg = self.pg
        inp = self.box_of(pg.locator("input[name=START_DATE]").first)
        self.spot(inp, self.now(), self.now() + 1.2, 8)
        self.go_click(inp, 0.7)
        pg.locator(".react-datepicker").first.wait_for(timeout=5000)
        self.sleep(0.3)
        self.spot(self.box_of(pg.locator(".react-datepicker").first), self.now(), end + 0.2, 4)
        self.sleep(max(0.4, self.dur[s.key] * 0.25))
        self.pick_day(NEW_DAY)

    def do_A3(self, s, end):                       # 종료 날짜 → 29일
        pg = self.pg
        if pg.locator(".react-datepicker").count():
            pg.keyboard.press("Escape"); self.sleep(0.2)
        inp = self.box_of(pg.locator("input[name=END_DATE]").first)
        self.spot(inp, self.now(), self.now() + 1.2, 8)
        self.go_click(inp, 0.7)
        pg.locator(".react-datepicker").first.wait_for(timeout=5000)
        self.sleep(0.3)
        self.spot(self.box_of(pg.locator(".react-datepicker").first), self.now(), end + 0.2, 4)
        self.sleep(max(0.6, self.dur[s.key] * 0.35))
        self.pick_day(NEW_DAY)
        if pg.locator(".react-datepicker").count():
            pg.keyboard.press("Escape"); self.sleep(0.2)

    def do_A4(self, s, end):                       # 일정 유형 → 교육
        pg = self.pg
        sel = self.box_of(self.modal("일정 추가").locator(".MuiSelect-select").first)
        self.spot(sel, self.now(), self.now() + 1.2, 8)
        self.go_click(sel, 0.7)
        lst = pg.locator("[role=listbox]").first
        lst.wait_for(timeout=5000)
        self.sleep(0.3)
        self.spot(self.box_of(lst), self.now(), end + 0.2, 4)
        first = self.box_of(pg.locator("li[role=option]").first)
        self.glide(first["x"] + 50, first["y"] + first["height"] / 2, 0.5)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        self.go_click(self.box_of(pg.locator("li[role=option]").filter(has_text=NEW_CAT).first), 0.6)
        self.sleep(0.3)

    def do_A5(self, s, end):                       # 제목·내용
        t = self.box_of(self.pg.locator("input[name=TITLE]").first)
        c = self.box_of(self.pg.locator("textarea[name=CONTENTS]").first)
        self.spot(self.union(t, c, pad=10), self.now(), end + 0.2, 0)
        self.type_in("input[name=TITLE]", NEW_TITLE, move=0.5, delay=0.06)
        self.sleep(0.15)
        self.type_in("textarea[name=CONTENTS]", NEW_BODY, move=0.4, delay=0.03)

    def do_A6(self, s, end):                       # 등록(막힘) → 창 닫기(←)
        pg = self.pg
        m = self.modal("일정 추가")
        loc = m.locator("button").filter(has_text="등록").last
        loc.scroll_into_view_if_needed(timeout=5000)
        btn = self.box_of(loc)
        s0 = self.now()
        self.glide(btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2, 0.8)
        self.spot(btn, s0 + 0.3, end + 0.2, 10)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.8)
        if self.mode == "dry" and not any("schedule" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", "등록 단추가 눌리지 않았어요")
        self.close_form("일정 추가")

    def close_form(self, title):
        pg = self.pg
        for _ in range(3):                         # 제목 옆 뒤로(←, 첫 IconButton)로 닫는다
            f = self.modal(title)
            if not f.count() or not f.is_visible():
                break
            back = f.locator("button.MuiIconButton-root").first.bounding_box(timeout=3000)
            if back:
                self.glide(back["x"] + back["width"] / 2, back["y"] + back["height"] / 2, 0.4); self.click(); self.nozoom()
            else:
                pg.keyboard.press("Escape")
            self.sleep(0.6)

    # ── 3단계 ──
    def do_E1(self, s, end):                       # 달력 위 일정(17·18 여러 날, 31)
        a, b = self.day_cell("17"), self.day_cell("18")
        z = self.day_cell("31")
        self.spot(self.union(a, b, pad=4), self.now(), self.now() + max(1.6, self.dur[s.key] * 0.5), 0)
        self.glide(a["x"] + 60, a["y"] + 40, 0.7)
        self.sleep(0.5)
        self.glide(b["x"] + 60, b["y"] + 40, 0.6)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.spot(z, self.now(), end + 0.2, 4)
        self.glide(z["x"] + 60, z["y"] + 40, 0.7)

    def do_E2(self, s, end):                       # 25일 → 오른쪽 일정 → 일정 창
        pg = self.pg
        c = self.day_cell("25")
        self.spot(c, self.now(), self.now() + 1.4, 4)
        self.go_click(self.rect(c["x"] + 30, c["y"] + 10, 30, 20), 0.7)
        pg.get_by_text("2026년 10월 25일").first.wait_for(timeout=5000)
        self.sleep(0.4)
        item = self.right_item("10월 승급심사")
        if not item:
            raise SceneError(s, "그날 일정", "오른쪽에서 일정을 찾지 못했어요")
        self.spot(self.rect(1083, item["y"] - 14, 808, 70), self.now(), end, 0)
        self.sleep(max(0.5, self.dur[s.key] * 0.3))
        self.go_click(self.rect(item["x"] + 40, item["y"], 40, item["height"]), 0.7)
        self.modal("저장").locator("input[name=TITLE]").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_E3(self, s, end):                       # 저장·삭제(가리키기만) → 창 닫기
        pg = self.pg
        m = self.modal("저장")
        sv = self.box_of(m.locator("button").filter(has_text="저장").last)
        dl = self.box_of(m.locator("button").filter(has_text="삭제").last)
        t = self.box_of(m.locator("textarea[name=CONTENTS]").first)
        self.spot(t, self.now(), self.now() + 1.4, 8)
        self.glide(t["x"] + 200, t["y"] + 30, 0.6)
        self.sleep(max(0.5, self.dur[s.key] * 0.2))
        self.spot(sv, self.now(), self.now() + max(1.2, self.dur[s.key] * 0.3), 8)
        self.glide(sv["x"] + sv["width"] / 2, sv["y"] + sv["height"] / 2, 0.6)
        self.sleep(max(0.8, self.dur[s.key] * 0.3))
        self.spot(dl, self.now(), end + 0.2, 8)
        self.glide(dl["x"] + dl["width"] / 2, dl["y"] + dl["height"] / 2, 0.6)
        self.wait_until(end - 0.1)

    def do_M1(self, s, end):
        self.close_form("저장")
        self.phone(s, end, 1, tap=True)

    def do_M2(self, s, end): self.phone(s, end, 2)


maker.Recorder = Ep14Recorder


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

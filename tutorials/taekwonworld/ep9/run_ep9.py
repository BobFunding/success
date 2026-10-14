"""9편(출결 관리) 만들기: 8편 녹화기(로그인·도장 선택·공통 동작) + 이 편만의 동작.
사용: python run_ep9.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 예시 날짜는 기록이 없는 2026-10-13.
- 저장: 출결 저장(/v2/student/attendance/update)은 서버로 보내지 않고 이 녹화기가 '성공'으로 답한다.
  저장한 값은 녹화기 안에만 두었다가, 화면이 그날 출결을 다시 읽을 때(read/day) 실제 응답에 덧붙여 보여 준다
  → 화면에서는 출석·등원 시간이 들어간 것처럼 보이지만 실제 기록·학부모님 알림은 생기지 않는다. 그 밖의 쓰기는 막는다.
- 흐림: 출결 화면의 수련생 이름(사진 옆 글자). 휴대폰·QR 앱 그림은 미리 흐린 사본(phone/).
- '현재 시간'이 한국 시간으로 들어가게 브라우저 시간대를 Asia/Seoul 로 둔다(컨테이너 시계는 UTC).
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep8"))
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep8 as E8                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

DAY = "20261013"                                              # 예시 날짜(기록 없음)
REGIST = "https://taekwonworld.net/attendance/regist?class=0"
STATUS = "https://taekwonworld.net/attendance/status?class=0&y=2026&m=10"
PHONE = (HERE / "phone" / "phone.html").as_uri()
QR = (HERE / "phone" / "qr.html").as_uri()
KID = "김태풍"                                                 # 한 명씩 보여 줄 줄(이름은 화면에서 흐림)
MEMO = "감기로 결석"
BULK = ("김테스트", "윤승호", "이송희")                    # 일괄 출석 예시 세 줄(이름은 화면에서 흐림)

# 출결 화면: 사진 옆 수련생 이름 흐림(조회 화면의 툴팁 포함)
BLUR9 = r"""(() => {
  const run = () => {
    if (!/\/attendance\//.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!/^[가-힣]{2,4}$/.test(t) || /^(출석|결석|지각|메모|전체반|조회)$/.test(t)) continue;
      if (e.getBoundingClientRect().x < 240) continue;                  // 왼쪽 메뉴는 그대로
      for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
        if (p.querySelector('img[alt=Profile], img[src*="profile"], img[src*="student/img"]')) { e.classList.add('__tm_blur'); break; }
    }
    for (const t of document.querySelectorAll('[role=tooltip]')) t.classList.add('__tm_blur_names');
  };
  setInterval(run, 120);
})()"""


class Ep9Recorder(E8.Ep8Recorder):
    fake = {}                                                 # {날짜: {수련생 번호: 출결 정보}}

    def scenario(self) -> None:
        self.fake = {}
        self.pg.add_init_script(BLUR9)
        try:                                                  # '현재 시간'을 한국 시간으로
            self.pg.context.new_cdp_session(self.pg).send("Emulation.setTimezoneOverride", {"timezoneId": "Asia/Seoul"})
        except Exception:
            pass
        super(E8.Ep8Recorder, self).scenario()

    def block_requests(self) -> None:
        if self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            api = "taekwonworld" in q.url and q.resource_type in ("xhr", "fetch")
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            if api and write and "/attendance/update" in q.url:          # 출결 저장 → 녹화기 안에만 두고 성공으로 답함
                try:
                    for it in json.loads(q.post_data or "[]"):
                        d = self.fake.setdefault(it.get("ATTEND_YMD") or DAY, {}).setdefault(it["STUDENT_ID"], {})
                        d.update({k: v for k, v in it.items() if v is not None and k != "STUDENT_ID"})
                except Exception:
                    pass
                self.log.setdefault("faked", []).append(f"{q.method} {q.url[-30:]}")
                r.fulfill(status=200, content_type="application/json", body="{}")
                return
            if api and q.method == "GET" and "/attendance/read/day/" in q.url:
                ymd = q.url.split("/read/day/")[1].split("/")[0]
                if self.fake.get(ymd):
                    res = r.fetch()
                    rows = res.json()
                    for row in rows:
                        f = self.fake[ymd].get(row.get("STUDENT_ID"))
                        if f:
                            row["ATTEND_INFO"] = {**(row.get("ATTEND_INFO") or {}), "ATTEND_YMD": ymd, **f}
                    r.fulfill(response=res, body=json.dumps(rows, ensure_ascii=False), content_type="application/json")
                    return
            if api and write and self.blocked(pg.url or "") and "read" not in q.url.lower():
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
                return
            r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    # ── 공통 ──
    def row_cell(self, name, idx):
        """name 줄의 idx 번째 칸(0 체크 · 1 이름 · 2 출석번호 … 6 출결 · 7 등원 · 8 하원 · 9 메모) 안쪽 상자."""
        return self.pg.evaluate("""([n, i]) => { const e=[...document.querySelectorAll('div')].find(e=>!e.childElementCount && (e.innerText||'').trim()===n);
            let row=e; while(row && !(row.className||'').includes('h-[60px]')) row=row.parentElement; if (!row) return null;
            const c=row.children[i]; const t=c.firstElementChild||c; const r=t.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", [name, idx])

    def column(self, header, pad_w=20):
        """표 머리 글자(header) 아래 세로 줄 전체."""
        return self.pg.evaluate("""([h, pw]) => { let e=null, a=1e9;                 // 머리 글자 옆에 정렬 아이콘이 붙어 있어 가장 작은 상자를 고른다
            for (const c of document.querySelectorAll('div, span, p, th')) { const r=c.getBoundingClientRect();
              if ((c.innerText||'').trim()!==h || r.x<240 || r.width<=0 || r.y>260) continue; if (r.width*r.height<a) { a=r.width*r.height; e=c; } }
            if (!e) return null; const r=e.getBoundingClientRect(); const rows=[...document.querySelectorAll('div')].filter(d=>(d.className||'').includes('h-[60px]'));
            const last=rows.length ? rows[rows.length-1].getBoundingClientRect() : r; return {x:r.x-pw, y:r.y-14, width:r.width+2*pw+40, height:last.bottom-r.y+14}; }""", [header, pad_w])

    def close_modals(self):
        pg = self.pg
        for _ in range(4):
            if not pg.locator(".MuiModal-root").count():
                return
            close = pg.get_by_text("닫기", exact=True)
            if close.count():
                self.go_click(self.box_of(close.last), 0.4)
            else:
                self.glide(1880, 1050, 0.4); self.sleep(0.1); self.click()
            self.sleep(0.6)

    def menu_item(self, top, item):
        """왼쪽 메뉴 top 을 펼치고(이미 펼쳐 있으면 그대로) item 의 자리."""
        it = self.side(item)
        if not it:
            t = self.side(top)
            self.go_click(t, 0.6)
            self.sleep(0.5)
            it = self.side(item)
        return it

    # ── 1단계 ──
    def do_P1(self, s, end):                       # 안내 창 → 창 닫기('다시보지않기'는 누르지 않음)
        pg = self.pg
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        btn = pg.locator("button:text-is('창 닫기')").first
        b = self.box_of(btn)
        s0 = self.now()
        self.spot(dlg, s0, s0 + max(1.4, self.dur[s.key] * 0.45), 6)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(b, self.now() - 0.5, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        btn.wait_for(state="hidden", timeout=5000)

    def do_P2(self, s, end):                       # 왼쪽 메뉴 출결 → 출결 관리
        pg = self.pg
        top = self.side("출결")
        s0 = self.now()
        self.glide(top["x"] + 110, top["y"] + top["height"] / 2, 0.8)
        self.spot(top, s0, s0 + 1.6, 6)
        self.sleep(0.3)
        self.click()
        self.sleep(0.6)
        it = self.side("출결 관리")
        if not it:
            raise SceneError(s, "왼쪽 메뉴", "출결 관리 메뉴를 찾지 못했어요")
        self.sleep(max(0.3, self.dur[s.key] * 0.35))
        self.glide(it["x"] + 80, it["y"] + it["height"] / 2, 0.6)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url("**/attendance/regist**", timeout=20000)
        pg.get_by_text("출결 관리 사용 가이드").first.wait_for(timeout=20000)
        self.sleep(0.4)

    def do_P3(self, s, end):                       # 출결 관리 사용 가이드 → 닫기
        pg = self.pg
        guide = self.guide_box("출결 관리 사용 가이드")
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
        self.close_modals()
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    def do_P4(self, s, end):                       # 머리줄 + 첫 줄
        head = self.column("출석번호")
        first = self.row_cell(KID, 1)
        memo = self.row_cell(KID, 9)
        if not (head and first and memo):
            raise SceneError(s, "수련생 목록", f"출결 표를 찾지 못했어요 {head} {first} {memo}")
        band = self.rect(first["x"] - 70, head["y"], memo["x"] + memo["width"] - first["x"] + 110, first["y"] + first["height"] + 14 - head["y"])
        s0 = self.now()
        self.spot(band, s0, end + 0.2, 0)
        self.glide(first["x"] + 300, first["y"] + first["height"] / 2, 0.9)
        self.glide(memo["x"] - 60, memo["y"] + memo["height"] / 2, max(1.2, self.dur[s.key] * 0.55))

    def do_P5(self, s, end):                       # 출석번호 세로 줄
        col = self.column("출석번호", 24)
        s0 = self.now()
        self.spot(col, s0, end + 0.2, 0)
        num = self.row_cell(KID, 2)
        self.glide(num["x"] + 30, num["y"] + num["height"] / 2, 0.8)
        self.glide(num["x"] + 30, num["y"] + 300, max(1.0, self.dur[s.key] * 0.5))

    # ── 2단계: 큐알 앱(공식 가이드 그림) ──
    def qr(self, s, end, page, hot, first=False):
        pg = self.pg
        if first:
            pg.goto(QR, wait_until="load")
            pg.wait_for_timeout(1200)                 # 글꼴·그림
        pg.evaluate(f"show({page}, {hot})")
        self.sleep(0.5)
        b = self.box_of(pg.locator("#hot"))
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.15))
        self.glide(b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.55, 0.8)
        self.spot(self.rect(b["x"] - 6, b["y"] - 6, b["width"] + 12, b["height"] + 12), s0, end + 0.2, 0)

    def do_Q1(self, s, end): self.qr(s, end, 1, 1, first=True)
    def do_Q2(self, s, end): self.qr(s, end, 1, 1)
    def do_Q3(self, s, end): self.qr(s, end, 1, 2)
    def do_Q4(self, s, end): self.qr(s, end, 1, 5)
    def do_R1(self, s, end): self.qr(s, end, 2, 1)
    def do_R2(self, s, end): self.qr(s, end, 2, 2)
    def do_R3(self, s, end): self.qr(s, end, 2, 3)

    # ── 2단계: 웹에서 직접 ──
    def do_W1(self, s, end):                       # 출결 관리로 돌아와 화면 전체
        pg = self.pg
        pg.goto(REGIST, wait_until="domcontentloaded")
        pg.get_by_text("출결 관리", exact=True).first.wait_for(timeout=20000)
        self.sleep(1.2)
        if pg.locator(".MuiModal-root").count():                       # 가이드가 또 뜨면 바로 닫는다
            pg.get_by_text("닫기", exact=True).last.click()
            self.sleep(0.6)
        top = self.box_of(pg.locator("input[name=att_date]").first)
        bulk = self.box_of(pg.locator("button:has-text('일괄 결석')").first)
        s0 = self.now()
        area = self.rect(top["x"] - 70, top["y"] - 16, bulk["x"] + bulk["width"] - top["x"] + 86, 140)
        self.spot(area, s0, end + 0.2, 0)
        self.glide(top["x"] + 300, top["y"] + 60, 0.9)

    def do_W2(self, s, end):                       # 날짜 → 10월 13일
        pg = self.pg
        inp = pg.locator("input[name=att_date]").first
        b = self.box_of(inp)
        s0 = self.now()
        self.spot(b, s0, s0 + 1.8, 8)
        self.go_click(b, 0.7)
        self.sleep(0.6)
        day = pg.locator(".react-datepicker__day--013:not(.react-datepicker__day--outside-month)").first
        cal = pg.locator(".react-datepicker").first.bounding_box()
        db = self.box_of(day)
        if cal:
            self.spot(self.rect(cal["x"] - 6, cal["y"] - 6, cal["width"] + 12, cal["height"] + 12), self.now() - 0.2, self.now() + 1.6, 0)
        self.sleep(max(0.4, self.dur[s.key] * 0.25))
        self.spot(self.rect(db["x"] - 4, db["y"] - 4, db["width"] + 8, db["height"] + 8), self.now(), self.now() + 1.0, 0)
        self.go_click(db, 0.6)
        pg.wait_for_function("() => document.querySelector('input[name=att_date]').value.includes('13일')", timeout=8000)
        self.sleep(1.0)
        self.spot(b, self.now() - 0.6, end + 0.2, 8)

    def do_W3(self, s, end):                       # 비어 있는 출결 칸들
        col = self.column("출결", 18)
        s0 = self.now()
        self.spot(col, s0, end + 0.2, 0)
        c = self.row_cell(KID, 6)
        self.glide(c["x"] + 40, c["y"] + c["height"] / 2, 0.8)
        self.glide(c["x"] + 40, c["y"] + 360, max(1.0, self.dur[s.key] * 0.5))
        if self.mode == "dry" and (self.pg.evaluate("(n) => document.body.innerText.includes(n)", KID) is False):
            raise SceneError(s, "빈 출결 칸", "수련생 줄을 찾지 못했어요")

    def do_W4(self, s, end):                       # 출결 칸 → 출석/결석/지각 → 출석
        pg = self.pg
        c = self.row_cell(KID, 6)
        s0 = self.now()
        self.go_click(c, 0.7)                      # 한 번 누르면 고르는 칸으로 바뀌고
        self.sleep(0.4)
        sel = self.row_cell(KID, 6)
        self.glide(sel["x"] + sel["width"] / 2, sel["y"] + sel["height"] / 2, 0.15)
        self.click()                               # 한 번 더 누르면 목록이 열린다
        pg.locator("li[role=option]").first.wait_for(timeout=5000)
        self.sleep(0.2)
        menu = self.box_of(pg.locator("[role=listbox]").first)
        self.spot(self.union(sel, menu, pad=6), s0 + 0.6, end + 0.2, 0)
        opts = pg.locator("li[role=option]")
        for name in ("결석", "지각"):              # 고를 수 있는 것을 짚어 주고
            ob = self.box_of(opts.filter(has_text=name).first)
            self.glide(ob["x"] + 40, ob["y"] + ob["height"] / 2, 0.45)
            self.sleep(max(0.2, self.dur[s.key] * 0.08))
        self.wait_until(end - 0.8)
        self.go_click(self.box_of(opts.filter(has_text="출석").first), 0.45)
        self.sleep(0.6)
        if self.mode == "dry" and not self.log.get("faked"):
            raise SceneError(s, "출결 고르기", "저장 요청이 없었어요")

    def do_W5(self, s, end):                       # 세 명 체크 → 일괄 출석
        pg = self.pg
        s0 = self.now()
        first = None
        for n in BULK:
            b = self.row_cell(n, 0)
            if not b:
                raise SceneError(s, "일괄 출석", f"{n} 줄의 체크칸을 찾지 못했어요")
            first = first or b
            self.go_click(b, 0.5)
            self.sleep(0.15)
        self.spot(self.rect(first["x"] - 12, first["y"] - 18, 40, b["y"] + b["height"] - first["y"] + 36), s0, self.now() + 0.6, 0)
        btn = pg.locator("button:has-text('일괄 출석')").first
        bb = self.box_of(btn)
        self.glide(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, 0.8)
        self.spot(bb, self.now() - 0.5, end + 0.2, 8)
        self.wait_until(end - 0.4)
        self.click()
        self.sleep(1.0)
        col = self.column("출결", 18)
        self.spot(col, self.now() - 0.3, self.now() + 1.4, 0)
        if self.mode == "dry" and len(self.log.get("faked", [])) < 2:
            raise SceneError(s, "일괄 출석", "일괄 출석 요청이 없었어요")

    def do_W6(self, s, end):                       # 등원 시간 칸 → 창
        pg = self.pg
        c = self.row_cell(KID, 7)
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.spot(self.rect(c["x"] - 10, c["y"] - 10, c["width"] + 20, c["height"] + 20), s0, self.now() + 1.0, 0)
        self.go_click(c, 0.7)
        pg.get_by_text("등원 시간", exact=True).last.wait_for(timeout=5000)
        self.sleep(0.4)
        m = self.guide_box_small("등원 시간")
        if m:
            self.spot(m, self.now(), end + 0.2, 4)

    def guide_box_small(self, title):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('.MuiModal-root *')].find(e=>e.childElementCount<=1 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>300 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""", title)

    def do_W7(self, s, end):                       # 현재 시간 체크
        pg = self.pg
        m = pg.locator(".MuiModal-root").last
        lab = self.box_of(m.get_by_text("현재 시간", exact=True))
        tin = self.box_of(m.locator("input[type=text]").first)
        s0 = self.now()
        self.spot(self.union(tin, lab, pad=10), s0, end + 0.2, 0)
        self.go_click(self.rect(lab["x"] - 22, lab["y"], 18, lab["height"]), 0.7)   # 체크칸(글자 왼쪽)
        self.sleep(0.5)

    def do_W8(self, s, end):                       # 앱 알림 보냄 → 저장(화면에서만)
        pg = self.pg
        m = pg.locator(".MuiModal-root").last
        send = m.locator("input[name=send_code]").first
        rb = self.box_of(send)
        lab = self.box_of(m.get_by_text("앱 알림", exact=True))
        s0 = self.now()
        self.spot(self.union(lab, rb, self.box_of(m.locator("input[name=send_code]").nth(1)), pad=12), s0, s0 + max(1.8, self.dur[s.key] * 0.5), 0)
        self.go_click(rb, 0.7)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        save = self.box_of(m.locator("button:text-is('저장')"))
        self.glide(save["x"] + save["width"] / 2, save["y"] + save["height"] / 2, 0.7)
        self.spot(save, self.now() - 0.4, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(1.2)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "저장", "등원 시간 창이 닫히지 않았어요")
        c = self.row_cell(KID, 7)
        self.spot(self.rect(c["x"] - 10, c["y"] - 10, c["width"] + 20, c["height"] + 20), self.now() - 0.4, self.now() + 1.2, 0)

    def do_W9(self, s, end):                       # 메모 → 적어 보기(저장 안 하고 바깥을 눌러 닫음)
        pg = self.pg
        c = self.row_cell(KID, 9)
        s0 = self.now()
        self.spot(self.rect(c["x"] - 10, c["y"] - 10, c["width"] + 20, c["height"] + 20), s0, s0 + 1.2, 0)
        self.go_click(c, 0.8)
        pg.locator(".MuiModal-root textarea:not([aria-hidden=true])").first.wait_for(timeout=5000)
        self.sleep(0.3)
        m = self.guide_box_small("메모") or self.box_of(pg.locator(".MuiModal-root textarea:not([aria-hidden=true])").first)
        self.spot(m, self.now(), end + 0.2, 4)
        self.type_in(".MuiModal-root textarea:not([aria-hidden=true])", MEMO, move=0.5, delay=0.12)
        self.wait_until(end - 0.2)

    # ── 학부모님 휴대폰 ──
    def phone(self, s, end, n, hot=None, tap=False):
        pg = self.pg
        if not pg.url.startswith(PHONE):
            pg.goto(f"{PHONE}#{n}", wait_until="load")      # 처음부터 그 화면으로(첫 화면이 잠깐 비치지 않게)
            pg.wait_for_timeout(1200)
        pg.evaluate(f"show({n})")
        self.sleep(0.5)
        h = self.box_of(pg.locator("#zoom" if n <= 2 else f"#hot-{hot or n}"))   # 알림은 옆에 크게 보여 준 카드
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.15))
        self.glide(h["x"] + h["width"] * 0.6, h["y"] + h["height"] * 0.55, 0.8)
        if tap:
            self.sleep(0.2)
            self.click()                               # 누르는 모습(그림 위라 아무 일도 없음)
        self.spot(self.rect(h["x"] - 6, h["y"] - 6, h["width"] + 12, h["height"] + 12), s0, end + 0.2, 0)

    def do_M1(self, s, end): self.phone(s, end, 1)
    def do_M2(self, s, end): self.phone(s, end, 2)

    # ── 3단계 ──
    def do_C1(self, s, end):                       # 출결 > 조회
        pg = self.pg
        pg.goto(STATUS, wait_until="domcontentloaded")
        pg.get_by_text("출결 조회", exact=True).first.wait_for(timeout=20000)
        self.sleep(1.2)
        if pg.locator(".MuiModal-root").count():
            pg.get_by_text("닫기", exact=True).last.click()
            self.sleep(0.6)
        top, it = self.side("출결"), self.side("조회")
        if not (top and it):
            raise SceneError(s, "왼쪽 메뉴", "출결·조회 메뉴를 찾지 못했어요")
        s0 = self.now()
        self.glide(top["x"] + 110, top["y"] + top["height"] / 2, 0.8)
        self.spot(top, s0, s0 + 1.4, 6)
        self.sleep(0.6)
        self.glide(it["x"] + 80, it["y"] + it["height"] / 2, 0.6)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)

    def do_C2(self, s, end):                       # ○/× 표시 + 오른쪽 합계
        pg = self.pg
        leg = pg.evaluate("""() => { const es=[...document.querySelectorAll('*')].filter(e=>!e.childElementCount && /^(출석|결석)$/.test((e.innerText||'').trim()));
            const rs=es.map(e=>e.getBoundingClientRect()).filter(r=>r.y<190 && r.x>1500); if (!rs.length) return null;
            const x0=Math.min(...rs.map(r=>r.x))-40, x1=Math.max(...rs.map(r=>r.right)); return {x:x0,y:rs[0].y-8,width:x1-x0+8,height:rs[0].height+16}; }""")
        tot = self.column("출석", 10)
        s0 = self.now()
        if leg:
            self.spot(leg, s0, s0 + max(1.8, self.dur[s.key] * 0.45), 6)
            self.glide(leg["x"] + leg["width"] / 2, leg["y"] + leg["height"] + 20, 0.8)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        if tot:
            band = self.rect(tot["x"] - 20, tot["y"], 1890 - tot["x"] + 20, tot["height"])
            self.glide(band["x"] + band["width"] / 2, band["y"] + 100, 0.8)
            self.spot(band, self.now() - 0.4, end + 0.2, 0)

    def do_C3(self, s, end):                       # 14일 칸(첫 줄)에 마우스 올리기
        pg = self.pg
        pos = pg.evaluate("""(n) => { const h=[...document.querySelectorAll('*')].filter(e=>!e.childElementCount && (e.innerText||'').trim()==='14').map(e=>e.getBoundingClientRect()).find(r=>r.y<260 && r.x>800);
            const e=[...document.querySelectorAll('div, span, p')].find(e=>!e.childElementCount && (e.innerText||'').trim()===n);
            if (!h || !e) return null; const r=e.getBoundingClientRect(); return {x:h.x+h.width/2, y:r.y+r.height/2}; }""", KID)
        if not pos:
            raise SceneError(s, "날짜 칸", "14일 칸을 찾지 못했어요")
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.2))
        self.glide(pos["x"], pos["y"], 0.9)
        self.sleep(0.6)
        tip = pg.locator("[role=tooltip]").first
        tb = tip.bounding_box() if tip.count() else None
        cell = self.rect(pos["x"] - 18, pos["y"] - 30, 36, 60)
        self.spot(self.union(cell, tb, pad=6) if tb else cell, s0 + 1.0, end + 0.2, 0)

    def do_M3(self, s, end): self.phone(s, end, 3, tap=True)
    def do_M4(self, s, end): self.phone(s, end, 4)
    def do_M5(self, s, end): self.phone(s, end, 4, hot=5)


maker.Recorder = Ep9Recorder


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

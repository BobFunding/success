"""10편(납부 설정·청구서 발행) 만들기: 8편 녹화기(로그인·도장 선택·공통 동작) + 이 편만의 동작.
사용: python run_ep10.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 1·2단계: 데모 도장 '태권월드 태권도장'(결제서비스 미가입 → 청구서 발행은 'PG 가입신청' 안내).
- 3단계: 같은 계정의 결제서비스 가입 시험 도장('경희대SJC 결제테스트', 화면에서 이름 흐림)으로 옮겨 청구서 발행.
- 안전: /bill 화면의 쓰기 요청은 모두 막는다(설정 저장 포함). 발행 확인 창의 [발행]은 가리키기만 하고 [취소]로 닫는다.
- 흐림: 시험 도장 이름·주소·전화, 수련생 이름·전화번호(청구서 추가 창, 청구서 줄, 미리보기).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep8"))
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep8 as E8                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

PHONE = (HERE / "phone" / "phone.html").as_uri()
PG_DOJANG = "경희대SJC 결제테스트"                              # 결제서비스에 가입된 시험 도장(화면에서 흐림)
KID = "김태풍"                                                 # 청구서 예시 수련생(이름·번호는 화면에서 흐림)
AMOUNT = "150000"
INFO = "10월 수련비 안내드립니다."
NEW_ITEM = "차량비"

# 납부 화면: 시험 도장 이름·주소·전화, 수련생 이름·전화번호 흐림
BLUR10 = r"""(() => {
  const phone = /^0\d{1,2}-?\d{3,4}-?\d{4}$/, addr = /(구|로|길)\s?\d|\d+층$/;
  const keep = /^(\d[\d,]*\s?원|\d+일|\d+원|수련비|도복비|띠비|승급비|보호자.*|본인|미리보기|추가|조회|전체반|\+|-|청구서|미납|납부)$/;
  const run = () => {
    for (const e of document.querySelectorAll('p, div, span')) {          // 왼쪽 위 도장 이름(시험 도장만)
      if (!e.childElementCount && (e.innerText || '').includes('결제테스트')) e.classList.add('__tm_blur');
    }
    if (!/\/bill\//.test(location.pathname)) return;
    for (const e of document.querySelectorAll('p, div, span, td')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!t) continue;
      if (phone.test(t.replace(/\s/g, '')) || addr.test(t)) { e.classList.add('__tm_blur'); continue; }
      const row = e.closest('.MuiModal-root [class*="h-[60px]"], .MuiModal-root tr, form [class*="h-["]');
      if (row && (row.querySelector('input[type=checkbox]') || row.querySelector('input[name^=bill_list]')) && !keep.test(t)
          && e.getBoundingClientRect().x < 900) e.classList.add('__tm_blur');
    }
    document.querySelectorAll('input[name$=BUYER_PHONE_NUMBER]').forEach(i => i.classList.add('__tm_blur'));
  };
  setInterval(run, 120);
})()"""


class Ep10Recorder(E8.Ep8Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR10)
        super(E8.Ep8Recorder, self).scenario()

    # ── 공통 ──
    def spin_wait(self, sec=20):
        pg = self.pg
        for _ in range(int(sec / 0.25)):
            if not pg.locator(".MuiCircularProgress-root").count():
                return
            pg.wait_for_timeout(250)

    def holder_box(self, text, mw=300, mh=80):
        return self.pg.evaluate("""([w, mw, mh]) => { let t=null, a=1e12;
            for (const e of document.querySelectorAll('p, div, span, h1, h2, h3, button')) { const s=(e.innerText||'').trim(); const r=e.getBoundingClientRect();
              if (!s.startsWith(w) || r.x<240 || r.width<=0) continue; if (r.width*r.height<a) { a=r.width*r.height; t=e; } }
            let c=t; for (let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>mw && r.height>mh) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; }
            if (!t) return null; const r=t.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", [text, mw, mh])

    def menu_go(self, s, end, top, item, url_part):
        """왼쪽 메뉴 top 을 펼치고(이미 펼쳐 있으면 그대로) item 을 눌러 이동."""
        pg = self.pg
        s0 = self.now()
        it = self.side(item)
        if not it:
            t = self.side(top)
            self.glide(t["x"] + 110, t["y"] + t["height"] / 2, 0.8)
            self.spot(t, s0, s0 + 1.6, 6)
            self.sleep(0.2)
            self.click()
            self.sleep(0.6)
            it = self.side(item)
        if not it:
            raise SceneError(s, "왼쪽 메뉴", f"{item} 메뉴를 찾지 못했어요")
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.glide(it["x"] + 80, it["y"] + it["height"] / 2, 0.6)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url(f"**{url_part}**", timeout=20000)
        self.sleep(0.8)
        self.spin_wait()

    # ── 1단계: 결제서비스 확인하기 ──
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

    def do_P2(self, s, end):
        self.menu_go(s, end, "납부", "청구서 발행", "/bill/send")
        self.pg.get_by_text("태권월드 결제서비스 안내").first.wait_for(timeout=15000)

    def text_box(self, text):
        loc = self.pg.get_by_text(text).first
        loc.scroll_into_view_if_needed(timeout=5000)
        return self.box_of(loc)

    def do_P3(self, s, end):                       # 결제서비스 안내 머리(파란 띠)
        t = self.text_box("태권월드 결제서비스 안내")
        band = self.rect(t["x"] - 420, t["y"] - 30, t["width"] + 840, 250)
        s0 = self.now()
        self.spot(band, s0, end + 0.2, 0)
        self.glide(t["x"] + t["width"] * 0.6, t["y"] + 90, 0.9)

    def do_P4(self, s, end):                       # 무료 안내 → 정산 안내
        f1, f3 = self.text_box("가입비 무료"), self.text_box("청구서발송비 무료")
        s0 = self.now()
        free = self.union(f1, f3, pad=14)
        self.spot(free, s0, s0 + max(1.8, self.dur[s.key] * 0.45), 0)
        self.glide(free["x"] + free["width"] / 2, free["y"] + free["height"] + 20, 0.8)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        st = self.text_box("결제금액은 태권월드를 거치지않고")
        self.sleep(0.3)
        st = self.box_of(self.pg.get_by_text("결제금액은 태권월드를 거치지않고").first)
        self.glide(st["x"] + st["width"] * 0.5, st["y"] + st["height"] + 16, 0.8)
        self.spot(self.rect(st["x"] - 10, st["y"] - 8, st["width"] + 20, st["height"] + 16), self.now() - 0.4, end + 0.2, 0)

    def do_P5(self, s, end):                       # [PG 가입신청] 가리키기만(누르지 않음)
        btn = self.pg.locator("button:has-text('PG 가입신청')").first
        btn.scroll_into_view_if_needed(timeout=5000)
        self.sleep(0.4)
        b = self.box_of(btn)
        s0 = self.now()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0, end + 0.2, 10)

    # ── 2단계: 청구항목 정리하기 ──
    def do_S1(self, s, end):
        self.pg.evaluate("scrollTo(0, 0)")
        self.menu_go(s, end, "납부", "설정", "/bill/settings")
        self.pg.get_by_text("청구항목 관리").first.wait_for(timeout=15000)

    def items_box(self):
        ins = self.pg.locator("input[name^='prod_list']")
        first = self.box_of(self.pg.get_by_text("수련비", exact=True).first)
        last = self.box_of(ins.last)
        return self.rect(first["x"] - 20, first["y"] - 14, last["x"] + last["width"] - first["x"] + 80, last["y"] + last["height"] - first["y"] + 28)

    def do_S2(self, s, end):                       # 청구항목 목록
        b = self.items_box()
        s0 = self.now()
        self.spot(b, s0, end + 0.2, 0)
        self.glide(b["x"] + 200, b["y"] + 30, 0.8)
        self.glide(b["x"] + 200, b["y"] + b["height"] - 30, max(1.0, self.dur[s.key] * 0.5))

    def do_S3(self, s, end):                       # 새 항목 추가 → 차량비
        pg = self.pg
        add = self.box_of(pg.get_by_text("새 항목 추가").first)
        n0 = pg.locator("input[name^='prod_list']").count()
        s0 = self.now()
        self.spot(add, s0, s0 + 1.8, 8)
        self.go_click(add, 0.8)
        self.sleep(0.5)
        ins = pg.locator("input[name^='prod_list']")
        if ins.count() <= n0:
            raise SceneError(s, "새 항목 추가", "새 칸이 생기지 않았어요")
        new = ins.nth(ins.count() - 1)
        nb = self.box_of(new)
        sel = f"input[name='{new.get_attribute('name')}']"
        self.spot(self.rect(nb["x"] - 10, nb["y"] - 10, nb["width"] + 20, nb["height"] + 20), self.now(), end + 0.2, 0)
        self.type_in(sel, NEW_ITEM, move=0.5, delay=0.12)

    def do_S4(self, s, end):                       # 지우기 자리 가리키기 → 저장(막힘)
        pg = self.pg
        ins = pg.locator("input[name^='prod_list']")
        row = self.box_of(ins.nth(ins.count() - 2))
        s0 = self.now()
        # 줄 오른쪽 끝(지우기 단추 자리)을 가리킨다
        self.glide(row["x"] + row["width"] + 40, row["y"] + row["height"] / 2, 0.8)
        self.spot(self.rect(row["x"] - 10, row["y"] - 10, row["width"] + 90, row["height"] + 20), s0, s0 + max(1.6, self.dur[s.key] * 0.45), 0)
        self.sleep(max(0.6, self.dur[s.key] * 0.35))
        save = self.box_of(pg.locator("button[type=submit]:has-text('저장')").first)
        self.glide(save["x"] + save["width"] / 2, save["y"] + save["height"] / 2, 0.7)
        self.spot(save, self.now() - 0.4, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.6)

    # ── 3단계: 청구서 보내기(결제서비스 가입 도장) ──
    def do_C0(self, s, end):                       # 도장 목록에서 시험 도장으로 → 청구서 발행
        pg = self.pg
        pg.goto(E8.E3.E2.SELECT_URL, wait_until="domcontentloaded")
        card = pg.locator("div[slide]").filter(has=pg.locator("p", has_text=PG_DOJANG)).first
        card.wait_for(timeout=20000)
        self.sleep(0.6)
        go = card.get_by_text("관리하러 가기")
        go.scroll_into_view_if_needed(timeout=5000)
        self.sleep(0.3)
        b = self.box_of(go)
        s0 = self.now()
        self.spot(self.box_of(card), s0, s0 + 1.8, 6)
        self.go_click(b, 0.8)
        pg.wait_for_url("**/home", timeout=30000)
        pg.goto("https://taekwonworld.net/bill/send?y=2026&m=10", wait_until="domcontentloaded")
        pg.get_by_text("+ 청구서 추가").first.wait_for(timeout=30000)
        self.spin_wait()
        self.sleep(0.6)
        side = self.side("청구서 발행")
        if side:
            self.spot(side, self.now(), end + 0.2, 6)

    def do_C1(self, s, end):                       # + 청구서 추가 → 수련생 창
        pg = self.pg
        b = self.box_of(pg.get_by_text("+ 청구서 추가").first)
        s0 = self.now()
        self.spot(b, s0, end + 0.2, 8)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.go_click(b, 0.8)
        pg.locator(".MuiModal-root input[type=checkbox]").nth(1).wait_for(timeout=10000)
        self.sleep(0.4)

    def kid_check(self):
        return self.pg.evaluate("""(n) => { const e=[...document.querySelectorAll('.MuiModal-root *')].find(e=>!e.childElementCount && (e.innerText||'').trim()===n);
            if (!e) return null; let row=e; for (let i=0;i<8&&row;i++){ if (row.querySelector && row.querySelector('input[type=checkbox]')) break; row=row.parentElement; }
            const cb=row && row.querySelector('input[type=checkbox]'); if (!cb) return null; const r=cb.getBoundingClientRect(), q=row.getBoundingClientRect();
            return {cb:{x:r.x,y:r.y,width:r.width,height:r.height}, row:{x:q.x,y:q.y,width:q.width,height:q.height}}; }""", KID)

    def do_C2(self, s, end):                       # 김태풍 체크 → 추가
        pg = self.pg
        k = self.kid_check()
        if not k:
            raise SceneError(s, "수련생 고르기", "예시 수련생 줄을 찾지 못했어요")
        s0 = self.now()
        self.spot(k["row"], s0, s0 + max(2.0, self.dur[s.key] * 0.55), 4)
        self.go_click(k["cb"], 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.35))
        add = pg.locator(".MuiModal-root button").filter(has_text="추가").last
        ab = self.box_of(add)
        self.glide(ab["x"] + ab["width"] / 2, ab["y"] + ab["height"] / 2, 0.7)
        self.spot(ab, self.now() - 0.4, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        pg.locator("input[name='bill_list.0.AMOUNT']").wait_for(timeout=8000)
        self.sleep(0.4)

    def do_C3(self, s, end):                       # 청구항목(수련비) + 금액
        pg = self.pg
        item = self.box_of(pg.locator("input[name='bill_list.0.PRODUCT_NAME']").first.locator("xpath=.."))
        amt = self.box_of(pg.locator("input[name='bill_list.0.AMOUNT']").first)
        s0 = self.now()
        self.spot(self.union(item, amt, pad=10), s0, end + 0.2, 0)
        self.glide(item["x"] + item["width"] / 2, item["y"] + item["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.25))
        pg.locator("input[name='bill_list.0.AMOUNT']").first.fill("")
        self.type_in("input[name='bill_list.0.AMOUNT']", AMOUNT, move=0.6, delay=0.1)

    def month_plus(self):
        return self.pg.evaluate("""() => { const e=[...document.querySelectorAll('button, div, span')].filter(e=>(e.innerText||'').trim()==='+' && e.getBoundingClientRect().x>240 && e.getBoundingClientRect().y>200);
            if (!e.length) return null; const r=e[0].getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""")

    def do_C4(self, s, end):                       # 청구월 + (가리키기만)
        p = self.month_plus()
        if not p:
            raise SceneError(s, "청구월", "청구월 + 단추를 찾지 못했어요")
        s0 = self.now()
        self.glide(p["x"] + p["width"] / 2, p["y"] + p["height"] / 2, 0.9)
        self.spot(self.rect(p["x"] - 90, p["y"] - 14, 140, p["height"] + 28), s0, end + 0.2, 0)

    def do_C5(self, s, end):                       # 안내메시지 적기 + 메모 칸
        pg = self.pg
        info = "textarea[name='bill_list.0.INFO_MESSAGE']"
        ib = self.box_of(pg.locator(info).first)
        mb = self.box_of(pg.locator("textarea[name='bill_list.0.MEMO']").first)
        s0 = self.now()
        self.spot(self.rect(ib["x"] - 10, ib["y"] - 10, ib["width"] + 20, ib["height"] + 20), s0, s0 + max(2.2, self.dur[s.key] * 0.6), 0)
        self.type_in(info, INFO, move=0.7, delay=0.08)
        self.glide(mb["x"] + 40, mb["y"] + mb["height"] / 2, 0.7)
        self.spot(self.rect(mb["x"] - 10, mb["y"] - 10, mb["width"] + 20, mb["height"] + 20), self.now() - 0.3, end + 0.2, 0)

    def do_C6(self, s, end):                       # 일괄적용 버튼 줄
        pg = self.pg
        a = self.box_of(pg.locator("button:has-text('청구년월 일괄적용')").first)
        z = self.box_of(pg.locator("button:has-text('메모 일괄적용')").first)
        s0 = self.now()
        self.spot(self.union(a, z, pad=8), s0, end + 0.2, 0)
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2, 0.8)
        self.glide(z["x"] + z["width"] / 2, z["y"] + z["height"] / 2, max(1.0, self.dur[s.key] * 0.45))

    def do_C7(self, s, end):                       # 미리보기 → 창 → 바깥 눌러 닫기
        pg = self.pg
        b = self.box_of(pg.get_by_text("미리보기", exact=True).first)
        s0 = self.now()
        self.spot(b, s0, s0 + 1.4, 8)
        self.go_click(b, 0.8)
        pg.get_by_text("청구서 납부").first.wait_for(timeout=8000)
        self.sleep(0.4)
        m = self.holder_box("청구서 납부", 300, 300)
        if m:
            self.spot(m, self.now(), end - 0.2, 4)
        self.wait_until(end - 0.5)
        self.glide(1840, 1000, 0.4)
        self.sleep(0.05)
        self.click()
        pg.get_by_text("청구서 납부").first.wait_for(state="hidden", timeout=5000)

    def do_C8(self, s, end):                       # 청구서 발행 → 확인 창: 유의사항 체크, [발행] 가리키기만 → [취소]
        pg = self.pg
        btn = self.box_of(pg.locator("button[type=submit]:has-text('청구서 발행')").first)
        s0 = self.now()
        self.spot(btn, s0, s0 + 1.4, 8)
        self.go_click(btn, 0.8)
        m = pg.locator(".MuiModal-root").filter(has_text="위 유의사항을 확인하였습니다").last
        m.wait_for(timeout=8000)
        self.sleep(0.4)
        agree = m.get_by_text("위 유의사항을 확인하였습니다").first
        ab = self.box_of(agree)
        dlg = self.holder_box("총 1개의 청구서", 400, 300)
        if dlg:
            self.spot(dlg, self.now(), self.now() + max(1.6, self.dur[s.key] * 0.35), 4)
        self.go_click(self.rect(ab["x"] - 26, ab["y"], 20, ab["height"]), 0.8)       # 체크칸(글자 왼쪽)
        self.sleep(0.4)
        send = self.box_of(m.locator("button:text-is('발행')").first)
        self.glide(send["x"] + send["width"] / 2, send["y"] + send["height"] / 2, 0.7)      # 가리키기만
        self.spot(send, self.now() - 0.3, end - 0.4, 8)
        self.wait_until(end - 0.5)
        cancel = self.box_of(m.locator("button:text-is('취소')").first)
        self.go_click(cancel, 0.3)
        m.wait_for(state="detached", timeout=5000)
        if self.mode == "dry" and any("bill" in x.lower() and "send" in x.lower() for x in self.log.get("blocked", [])):
            raise SceneError(s, "발행", "발행 요청이 나가려 했어요 — 확인 필요")

    # ── 학부모님 휴대폰 ──
    def phone(self, s, end, n, tap=False):
        pg = self.pg
        if not pg.url.startswith(PHONE):
            pg.goto(f"{PHONE}#{n}", wait_until="load")      # 처음부터 그 화면으로(다른 화면이 비치지 않게)
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

    def do_M1(self, s, end): self.phone(s, end, 1)
    def do_M2(self, s, end): self.phone(s, end, 2)
    def do_M3(self, s, end): self.phone(s, end, 3, tap=True)
    def do_M4(self, s, end): self.phone(s, end, 4)


maker.Recorder = Ep10Recorder


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

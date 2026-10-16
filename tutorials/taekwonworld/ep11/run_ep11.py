"""11편(청구서 조회·납부 관리) 만들기: 10편 녹화기(납부 화면 흐림·메뉴 이동·공통 동작) + 이 편만의 동작.
사용: python run_ep11.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 시작(영상 밖): 로그인 뒤 결제서비스 가입 시험 도장 '경희대SJC 결제테스트'로 들어간다(청구서 조회에 1건).
- 2단계에서 '고려대 만덕태권도 결제테스트'로 옮겨 납부관리(현장결제 기록이 있음)를 보여 준다. 두 도장 이름은 흐림.
- 안전: /bill 화면의 쓰기 요청은 모두 막는다. 관리대장 생성·청구서 삭제는 가리키기만, 편집 창의 [저장]은 막힌 채로 누른다.
- 흐림: 도장 이름·주소·전화, 수련생 이름(사진 옆)·전화번호.
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

READ_DOJANG = "경희대SJC 결제테스트"
MANAGE_DOJANG = "고려대 만덕태권도 결제테스트"
MANAGE_URL = "https://taekwonworld.net/bill/management?y=2026&m=10&bt=0&pt=0&st=0"
UNPAID = "유지훈"                                             # 편집으로 보여 줄 미납 줄(이름은 화면에서 흐림)
MEMO = "현장 카드 결제"

# 납부관리·편집 창: 사진 옆 수련생 이름 흐림
BLUR11 = r"""(() => {
  const run = () => {
    if (!/\/bill\//.test(location.pathname)) return;
    for (const e of document.querySelectorAll('div, span, p')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!/^[가-힣A-Za-z0-9]{2,10}$/.test(t) || e.getBoundingClientRect().x < 240) continue;
      for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
        if (p.querySelector('img[alt=Profile], img[src*="profile"], img[src*="student/img"]')) { e.classList.add('__tm_blur'); break; }
    }
  };
  setInterval(run, 120);
})()"""


class Ep11Recorder(E10.Ep10Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR11)
        super().scenario()

    def pick_dojang(self, name):
        pg = self.pg
        pg.goto(E10.E8.E3.E2.SELECT_URL, wait_until="domcontentloaded")
        card = pg.locator("div[slide]").filter(has=pg.locator("p", has_text=name)).first
        card.wait_for(timeout=30000)
        return card

    def run_pre(self) -> None:
        """로그인(장면 표의 미리하기) 뒤 시험 도장으로 들어가 첫 화면까지(영상 밖)."""
        pg = self.pg
        ps = self.sc.pre_scenes[0]
        self.scene = ps
        pg.goto(self.sc.login_url, wait_until="networkidle", timeout=60000)
        for f in ps.fields:
            self.locate(f.target).fill(self.resolve_value(f), timeout=10000)
        self.locate(ps.button).click(timeout=10000)
        try:
            pg.wait_for_url(lambda u: "/account/login" not in u, timeout=30000)
        except Exception:
            raise SceneError(ps, "로그인", "로그인에 실패했어요. 보관함의 비밀번호를 확인해 주세요") from None
        self.pick_dojang(READ_DOJANG).get_by_text("관리하러 가기").click(timeout=20000)
        pg.wait_for_url("**/home", timeout=30000)
        self.scene = None

    def run_scene(self, s, last):
        if s.key == "R1":                          # 안내 창이 다 뜬 다음에 문장 시작
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super(E10.E8.E3.Ep3Recorder, self).run_scene(s, last)

    # ── 1단계: 청구서 조회하기 ──
    def do_R1(self, s, end): self.do_P1(s, end)

    def do_R2(self, s, end):
        self.menu_go(s, end, "납부", "청구서 조회", "/bill/read")
        self.pg.get_by_text("결제대기").first.wait_for(timeout=15000)

    def do_R3(self, s, end):                       # 발행·결제완료·결제대기·결제취소
        a = self.text_box("발행(결제취소 제외)")
        z = self.text_box("결제취소")
        band = self.rect(a["x"] - 30, a["y"] - 24, z["x"] + z["width"] - a["x"] + 200, 130)
        s0 = self.now()
        self.spot(band, s0, end + 0.2, 0)
        self.glide(a["x"] + 60, a["y"] + 50, 0.8)
        self.glide(z["x"] + 60, z["y"] + 50, max(1.2, self.dur[s.key] * 0.5))

    def do_R4(self, s, end):                       # 발행일 기준 / 청구월 기준 / 항목·상태 고르기(바꾸지 않고 짚기만)
        pg = self.pg
        a = self.box_of(pg.locator("button:has-text('발행일 기준')").first)
        z = self.box_of(pg.locator("button:has-text('조회')").last)
        s0 = self.now()
        self.spot(self.union(a, z, pad=10), s0, end + 0.2, 0)
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.25))
        b = self.box_of(pg.locator("button:has-text('청구월 기준')").first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.6)
        self.sleep(max(0.4, self.dur[s.key] * 0.2))
        self.glide(z["x"] - 260, z["y"] + z["height"] / 2, 0.8)

    def do_R5(self, s, end):                       # 청구서 한 줄
        pg = self.pg
        dele = self.box_of(pg.locator("button:has-text('청구서 삭제')").first)
        row = self.rect(300, dele["y"] - 30, dele["x"] + dele["width"] - 300 + 20, dele["height"] + 60)
        s0 = self.now()
        self.spot(row, s0, end + 0.2, 0)
        self.glide(row["x"] + 300, row["y"] + row["height"] / 2, 0.8)
        self.glide(dele["x"] - 420, row["y"] + row["height"] / 2, max(1.0, self.dur[s.key] * 0.5))

    def do_R6(self, s, end):                       # [청구서 삭제] 가리키기만
        b = self.box_of(self.pg.locator("button:has-text('청구서 삭제')").first)
        s0 = self.now()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 0.5, end + 0.2, 10)

    # ── 2단계: 납부 현황 보기 ──
    def do_G0(self, s, end):                       # 도장 목록 → 고려대 → 납부관리
        pg = self.pg
        card = self.pick_dojang(MANAGE_DOJANG)
        self.sleep(0.5)
        go = card.get_by_text("관리하러 가기")
        go.scroll_into_view_if_needed(timeout=5000)
        self.sleep(0.3)
        s0 = self.now()
        self.spot(self.box_of(card), s0, s0 + 1.6, 6)
        self.go_click(self.box_of(go), 0.8)
        pg.wait_for_url("**/home", timeout=30000)
        pg.goto(MANAGE_URL, wait_until="domcontentloaded")
        pg.get_by_text("관리대장 생성").first.wait_for(timeout=30000)
        self.spin_wait()
        self.sleep(0.8)

    def do_G1(self, s, end):                       # 항목·전체·납부·미납 카드
        a = self.text_box("항목")
        z = self.text_box("미납")
        band = self.rect(a["x"] - 20, a["y"] - 16, z["x"] + 200 - a["x"], 150)
        s0 = self.now()
        self.spot(band, s0, end + 0.2, 0)
        self.glide(a["x"] + 300, a["y"] + 60, 0.8)
        self.glide(z["x"] + 80, z["y"] + 60, max(1.2, self.dur[s.key] * 0.5))

    def do_G2(self, s, end):                       # [관리대장 생성] 가리키기만
        b = self.box_of(self.pg.locator("button:has-text('관리대장 생성')").first)
        s0 = self.now()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 0.4, end + 0.2, 10)

    def do_G3(self, s, end):                       # 납부상태 세로 줄
        col = self.column("납부상태", 20)
        if not col:
            raise SceneError(s, "납부상태", "납부상태 줄을 찾지 못했어요")
        s0 = self.now()
        self.spot(col, s0, end + 0.2, 0)
        self.glide(col["x"] + col["width"] / 2, col["y"] + 70, 0.8)
        self.glide(col["x"] + col["width"] / 2, col["y"] + col["height"] - 30, max(1.0, self.dur[s.key] * 0.5))

    def column(self, header, pad_w=20):
        return self.pg.evaluate("""([h, pw]) => { let e=null, a=1e9;
            for (const c of document.querySelectorAll('div, span, p, th')) { const r=c.getBoundingClientRect();
              if ((c.innerText||'').trim()!==h || r.x<240 || r.width<=0 || r.y<250) continue; if (r.width*r.height<a) { a=r.width*r.height; e=c; } }
            if (!e) return null; const r=e.getBoundingClientRect();
            const btns=[...document.querySelectorAll('button')].filter(b=>(b.innerText||'').trim()==='편집');
            const last=btns.length ? btns[btns.length-1].getBoundingClientRect() : r;
            return {x:r.x-pw, y:r.y-14, width:r.width+2*pw+30, height:last.bottom-r.y+24}; }""", [header, pad_w])

    # ── 3단계: 현장 결제 적기 ──
    def edit_btn(self):
        return self.pg.evaluate("""(n) => { const e=[...document.querySelectorAll('div, span, p')].find(e=>!e.childElementCount && (e.innerText||'').trim()===n);
            if (!e) return null; const y=e.getBoundingClientRect().y;
            const b=[...document.querySelectorAll('button')].filter(b=>(b.innerText||'').trim()==='편집').map(b=>b.getBoundingClientRect()).sort((p,q)=>Math.abs(p.y-y)-Math.abs(q.y-y))[0];
            const r=e.getBoundingClientRect(); return b ? {btn:{x:b.x,y:b.y,width:b.width,height:b.height}, row:{x:r.x-60,y:b.y-16,width:b.right-r.x+80,height:b.height+32}} : null; }""", UNPAID)

    def do_E1(self, s, end):                       # 미납 줄 → [편집]
        pg = self.pg
        k = self.edit_btn()
        if not k:
            raise SceneError(s, "편집", "미납 줄의 편집 단추를 찾지 못했어요")
        s0 = self.now()
        self.spot(k["row"], s0, s0 + max(1.8, self.dur[s.key] * 0.55), 0)
        self.glide(k["row"]["x"] + 400, k["row"]["y"] + k["row"]["height"] / 2, 0.8)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        self.glide(k["btn"]["x"] + k["btn"]["width"] / 2, k["btn"]["y"] + k["btn"]["height"] / 2, 0.7)
        self.spot(k["btn"], self.now() - 0.3, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        pg.get_by_text("납부내역 수정").first.wait_for(timeout=8000)
        self.sleep(0.4)

    def modal(self):
        return self.pg.locator(".MuiModal-root").filter(has_text="납부내역 수정").last

    def do_E2(self, s, end):                       # 납부상태 → 납부, 납부일·납부방법 짚기
        pg = self.pg
        m = self.modal()
        sel = m.locator(".MuiSelect-select").first
        sb = self.box_of(sel)
        s0 = self.now()
        self.spot(self.rect(sb["x"] - 10, sb["y"] - 10, sb["width"] + 20, sb["height"] + 20), s0, s0 + 2.2, 0)
        self.glide(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2, 0.8)
        self.sleep(0.1)
        self.click()
        opt = pg.locator("li[role=option]").filter(has_text="납부").first
        opt.wait_for(timeout=5000)
        self.sleep(0.3)
        self.go_click(self.box_of(opt), 0.5)
        self.sleep(0.4)
        dates = m.locator("input[type=text]")
        date = self.box_of(dates.nth(1)) if dates.count() > 1 else None
        way = m.locator(".MuiSelect-select").nth(1)
        wb = self.box_of(way)
        if date:
            self.glide(date["x"] + date["width"] / 2, date["y"] + date["height"] / 2, 0.6)
            self.spot(self.union(date, wb, pad=10), self.now() - 0.3, end + 0.2, 0)
        self.sleep(0.4)
        self.glide(wb["x"] + wb["width"] / 2, wb["y"] + wb["height"] / 2, 0.6)

    def do_E3(self, s, end):                       # 메모 → 저장(막힘) → 창 닫기([취소])
        pg = self.pg
        m = self.modal()
        memo = m.locator("input[type=text], textarea").last
        mb = self.box_of(memo)
        s0 = self.now()
        self.spot(self.rect(mb["x"] - 10, mb["y"] - 10, mb["width"] + 20, mb["height"] + 20), s0, s0 + 1.8, 0)
        self.glide(mb["x"] + 40, mb["y"] + mb["height"] / 2, 0.6)
        self.sleep(0.1)
        self.click()
        for ch in MEMO:
            pg.keyboard.type(ch)
            self.sleep(0.08)
        save = self.box_of(m.locator("button:text-is('저장')").first)
        self.glide(save["x"] + save["width"] / 2, save["y"] + save["height"] / 2, 0.6)
        self.spot(save, self.now() - 0.3, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.6)
        if self.modal().count():                   # 저장이 막혀 창이 남으면 [취소]로 닫는다
            self.go_click(self.box_of(self.modal().locator("button:text-is('취소')").first), 0.4)
            self.sleep(0.5)

    def do_E4(self, s, end):                       # 납부 통계차트 → 창(가만히 보여 줌)
        pg = self.pg
        b = self.box_of(pg.get_by_text("납부 통계차트").first)
        s0 = self.now()
        self.spot(b, s0, s0 + 1.4, 8)
        self.go_click(b, 0.8)
        pg.get_by_text("납부통계").first.wait_for(timeout=8000)
        self.sleep(0.6)
        box = self.holder_box("납부통계", 600, 400)
        if box:
            self.spot(box, self.now(), end + 0.2, 4)
            self.glide(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5, 0.8)


maker.Recorder = Ep11Recorder


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

"""8편(차량 등록) 만들기: 3편 녹화기(로그인·도장 선택·안내 창·쓰기 차단) + 이 편만의 동작.
사용: python run_ep8.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 저장: 차량 화면의 쓰기(carcreate 등)는 모두 막는다(요청차단: /manage/bus). 값은 모두 예시, 사진은 가짜 그림(sample_van.png).
  막힌 등록 뒤에는 [취소]로 창을 닫고, 이미 있는 '오전차량'을 눌러 조회·수정 창을 보여 준다([저장]·[차량 삭제]는 가리키기만).
- 이어서 관장님 첫 화면의 차량 현황, 7편에서 초대한 학부모님 앱의 차량(phone/phone.html)으로 '같은 차량을 함께 본다'를 보여 준다.
- 흐림: 목록·대시보드·차량 정보 창의 차량 번호, 차량 정보 창의 사진.
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep3 as E3                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

VAN = HERE / "sample_van.png"
PHONE = (HERE / "phone" / "phone.html").as_uri()
EX = dict(name="등원 1호차", number="12가 3456", kind="스타렉스", seats="12", memo="평일 오후 1시 30분 출발")

# 차량 화면: 목록의 차량 번호, '차량 정보'(이미 있는 차량) 창의 번호 칸·사진을 흐리게. 새로 적는 예시 번호는 그대로 둔다.
BLUR8 = r"""(() => {
  const plate = /^\d{1,3}\s?[가-힣]\s?\d{4}$/;
  const run = () => {
    if (!/\/manage\/bus/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('p, span, div, td')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      if (plate.test((e.innerText || '').trim())) e.classList.add('__tm_blur');
    }
    for (const m of document.querySelectorAll('.MuiModal-root')) {
      if (!(m.innerText || '').includes('차량 정보')) continue;
      m.querySelectorAll('input[name=car_number], img').forEach(x => x.classList.add('__tm_blur'));
    }
  };
  setInterval(run, 120);
})()"""


class Ep8Recorder(E3.Ep3Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR8)
        super().scenario()

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

    def union(self, *bs, pad=8):
        x0 = min(b["x"] for b in bs); y0 = min(b["y"] for b in bs)
        x1 = max(b["x"] + b["width"] for b in bs); y1 = max(b["y"] + b["height"] for b in bs)
        return self.rect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)

    def label_row(self, label, inp):
        """'차량 이름' 같은 글자와 그 칸을 함께 묶은 상자."""
        lab = self.pg.locator(".MuiModal-root").last.get_by_text(re.compile(r"^\s*" + label + r"\s*\*?\s*$")).first
        return self.union(self.box_of(lab), self.box_of(self.pg.locator(inp).first), pad=8)

    def type_in(self, sel, text, move=0.6, delay=0.09):
        b = self.box_of(self.pg.locator(sel).first)
        self.glide(b["x"] + 40, b["y"] + b["height"] / 2, move)
        self.sleep(0.1)
        self.typ(sel, text, delay)
        return b

    def guide_box(self, title):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>400 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""", title)

    # ── 1단계 ──
    def do_P1(self, s, end):                       # 안내 창 → 차량 등록(마지막 순서)
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("차량 등록")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/manage/bus", timeout=20000)
        self.pg.get_by_text("차량 사용 가이드").first.wait_for(timeout=20000)
        self.sleep(0.4)

    def do_P2(self, s, end):                       # 차량 사용 가이드 → 닫기
        pg = self.pg
        guide = self.guide_box("차량 사용 가이드")
        s0 = self.now()
        if guide:
            self.spot(guide, s0, s0 + max(1.2, self.dur[s.key] * 0.5), 6)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        b = self.box_of(pg.get_by_text("닫기", exact=True).last)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
        self.wait_until(end - 0.3)
        self.click()
        for _ in range(3):                         # 가이드가 한 번 더 뜨면 또 닫는다
            self.sleep(0.6)
            if not pg.locator(".MuiModal-root").count():
                break
            self.go_click(self.box_of(pg.get_by_text("닫기", exact=True).last), 0.4)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    # ── 2단계 ──
    def do_N1(self, s, end):                       # + 차량 등록
        btn = "button:has-text('차량 등록')"
        s0, b = self.approach(btn, end, frac=0.45)
        self.spot(b, s0, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.locator("input[name=car_name]").wait_for(timeout=10000)
        self.sleep(0.3)

    def do_F1(self, s, end):                       # 별표 두 칸 → 차량 이름
        s0 = self.now()
        need = self.union(self.label_row("차량 이름", "input[name=car_name]"),
                          self.label_row("차량 번호", "input[name=car_number]"), pad=0)
        self.spot(need, s0, s0 + max(1.4, self.dur[s.key] * 0.45), 4)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.type_in("input[name=car_name]", EX["name"])
        self.spot(self.label_row("차량 이름", "input[name=car_name]"), self.now() - 0.8, end + 0.2, 4)

    def do_F2(self, s, end):                       # 차량 번호
        s0 = self.now()
        self.spot(self.label_row("차량 번호", "input[name=car_number]"), s0, end + 0.2, 4)
        self.sleep(max(0.3, self.dur[s.key] * 0.2))
        self.type_in("input[name=car_number]", EX["number"])

    def do_F3(self, s, end):                       # 차종 · 인승(선택)
        s0 = self.now()
        both = self.union(self.label_row("차종", "input[name=car_type_code]"),
                          self.label_row("인승", "input[name=num_seater]"), pad=0)
        self.spot(both, s0, end + 0.2, 4)
        self.type_in("input[name=car_type_code]", EX["kind"])
        self.sleep(0.3)
        self.type_in("input[name=num_seater]", EX["seats"], move=0.5)

    def do_F4(self, s, end):                       # + 사진 추가 → 가짜 차량 그림
        btn = ".MuiModal-root button:has-text('사진 추가')"
        s0, b = self.approach(btn, end, frac=0.35)
        self.spot(b, s0, end + 0.2, 8)
        self.upload(btn, VAN, end)
        self.sleep(0.5)
        if self.mode == "dry" and not self.pg.get_by_text("차량 사진 (1/3)").count():
            raise SceneError(s, "사진 추가", "사진이 올라가지 않았어요")

    def photo_area(self):
        head = self.box_of(self.pg.get_by_text("차량 사진 (1/3)").first)
        note = self.box_of(self.pg.get_by_text("사진은 30MB 미만").first)
        right = self.box_of(self.pg.locator(".MuiModal-root button:has-text('사진 추가')").first)
        return self.rect(head["x"] - 10, head["y"] - 8, right["x"] + right["width"] - head["x"] + 20,
                         note["y"] + note["height"] - head["y"] + 16)

    def do_F5(self, s, end):                       # 파일 조건 + x(가리키기만 — 사진은 남김)
        s0 = self.now()
        area = self.photo_area()
        self.spot(area, s0, end + 0.2, 0)
        note = self.box_of(self.pg.get_by_text("사진은 30MB 미만").first)
        self.glide(note["x"] + note["width"] * 0.6, note["y"] + note["height"] / 2, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.45))
        img = self.pg.locator(".MuiModal-root img").last.bounding_box()
        if img:                                    # 사진 오른쪽 위의 x 자리
            self.glide(img["x"] + img["width"] + 2, img["y"] + 4, 0.7)

    def do_F6(self, s, end):                       # 차량 참고사항
        sel = ".MuiModal-root textarea:not([aria-hidden=true])"
        lab = self.box_of(self.pg.get_by_text("차량 참고사항", exact=True).first)
        box = self.box_of(self.pg.locator(sel).first)
        s0 = self.now()
        self.spot(self.union(lab, box, pad=8), s0, end + 0.2, 0)
        self.type_in(sel, EX["memo"], move=0.7, delay=0.07)

    # ── 3단계 ──
    def do_S1(self, s, end):                       # 등록(차단) → 취소로 닫기
        pg = self.pg
        btn = ".MuiModal-root button[type=submit]:has-text('등록')"
        s0, b = self.approach(btn, end, frac=0.45)
        self.spot(b, s0, end + 0.2, 8)
        self.wait_until(end - 0.35)
        self.click()
        self.sleep(0.8)
        self.go_click(self.box_of(pg.locator(".MuiModal-root button:text-is('취소')").first), 0.5)
        pg.locator("input[name=car_name]").wait_for(state="hidden", timeout=8000)
        if self.mode == "dry" and not any("car" in x.lower() for x in self.log.get("blocked", [])):
            raise SceneError(s, "등록", "등록 요청이 막히지 않았어요 — 확인 필요")

    def do_S2(self, s, end):                       # 목록 → 오전차량 열기
        pg = self.pg
        rows = [self.box_of(pg.get_by_text(n, exact=True).first) for n in ("오전차량", "오후차량")]
        body = self.rect(rows[0]["x"] - 40, rows[0]["y"] - 18, 1620, rows[1]["y"] + rows[1]["height"] - rows[0]["y"] + 36)
        s0 = self.now()
        self.glide(rows[0]["x"] + 600, rows[0]["y"] + rows[0]["height"] / 2, 0.9)
        self.spot(body, s0, s0 + max(1.6, self.dur[s.key] * 0.5), 0)
        self.sleep(max(0.8, self.dur[s.key] * 0.45))
        self.go_click(rows[0], 0.6)
        pg.get_by_text("차량 정보", exact=True).first.wait_for(timeout=10000)
        self.sleep(0.3)
        m = self.guide_box("차량 정보")
        if m:
            self.spot(m, self.now(), end + 0.2, 4)

    def do_S3(self, s, end):                       # [저장]·[차량 삭제] 가리키기만 → 창 닫기
        pg = self.pg
        save = self.box_of(pg.locator(".MuiModal-root button:text-is('저장')").first)
        dele = self.box_of(pg.locator(".MuiModal-root button:text-is('차량 삭제')").first)
        s0 = self.now()
        self.glide(save["x"] + save["width"] / 2, save["y"] + save["height"] / 2, 0.8)
        self.spot(save, s0, s0 + max(1.4, self.dur[s.key] * 0.45), 8)
        self.sleep(max(0.8, self.dur[s.key] * 0.4))
        self.glide(dele["x"] + dele["width"] / 2, dele["y"] + dele["height"] / 2, 0.7)
        self.spot(dele, self.now() - 0.5, end + 0.2, 8)
        self.wait_until(end)
        self.glide(1730, 990, 0.6)                 # 창 바깥(어두운 곳)을 눌러 닫는다(저장 안 함, Esc 는 안 먹음)
        self.sleep(0.1)
        self.click()
        pg.get_by_text("차량 정보", exact=True).first.wait_for(state="hidden", timeout=5000)

    def dash_box(self):
        """첫 화면 '차량 현황' 제목부터 마지막 차량 줄까지."""
        return self.pg.evaluate("""() => { const h=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()==='차량 현황');
            if (!h) return null; const r=h.getBoundingClientRect(); let bottom=r.bottom;
            for (const e of document.querySelectorAll('*')) { if (e.childElementCount) continue;
              const t=(e.innerText||'').trim(); if (!/^(미운행|운행중|운행 중)$/.test(t)) continue;
              const q=e.getBoundingClientRect(); if (q.x>r.x-40 && q.x<r.x+360 && q.y>r.y) bottom=Math.max(bottom, q.bottom+60); }
            return {x:r.x-14, y:r.y-12, width:340, height:bottom-r.y+16}; }""")

    def do_H1(self, s, end):                       # 왼쪽 메뉴 홈 → 안내 창 '창 닫기' → 차량 현황
        pg = self.pg
        home = self.side("홈")
        if not home:
            raise SceneError(s, "왼쪽 메뉴", "홈 메뉴를 찾지 못했어요")
        self.go_click(home, 0.6)
        pg.wait_for_url("**/home", timeout=20000)
        close = pg.locator("button:text-is('창 닫기')").first
        try:
            close.wait_for(timeout=8000)
            self.sleep(0.3)
            self.go_click(self.box_of(close), 0.5)          # '다시보지않기'는 누르지 않는다
            close.wait_for(state="hidden", timeout=5000)
        except Exception:
            pass                                            # 안내 창이 안 뜨면 그대로
        pg.get_by_text("차량 현황", exact=True).first.wait_for(timeout=10000)
        self.sleep(0.4)
        b = self.dash_box()
        if not b:
            raise SceneError(s, "차량 현황", "첫 화면에서 차량 현황을 찾지 못했어요")
        self.glide(b["x"] + b["width"] - 50, b["y"] + 80, 0.7)
        self.spot(b, self.now() - 0.3, end + 0.2, 0)

    # ── 학부모님 휴대폰(phone/phone.html) ──
    def phone(self, s, end, n, tap=False):
        pg = self.pg
        if n == 1:
            pg.goto(PHONE, wait_until="load")
            pg.wait_for_timeout(1200)                 # 글꼴·그림
        pg.evaluate(f"show({n})")
        self.sleep(0.5)
        hot = self.box_of(pg.locator(f"#hot-{n}"))
        s0 = self.now()
        self.sleep(max(0.4, self.dur[s.key] * 0.2))
        self.glide(hot["x"] + hot["width"] * 0.5, hot["y"] + hot["height"] * 0.5, 0.8)
        if tap:
            self.sleep(0.2)
            self.click()                               # 누르는 모습(그림 위라 아무 일도 없음)
        self.spot(self.rect(hot["x"] - 6, hot["y"] - 6, hot["width"] + 12, hot["height"] + 12), s0, end + 0.2, 0)

    def do_M1(self, s, end): self.phone(s, end, 1, tap=True)
    def do_M2(self, s, end): self.phone(s, end, 2)
    def do_M3(self, s, end): self.phone(s, end, 3)


maker.Recorder = Ep8Recorder


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

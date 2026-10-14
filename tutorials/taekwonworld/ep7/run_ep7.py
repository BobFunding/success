"""7편(수련생, 학부모 초대) 만들기: 3편 녹화기(로그인·도장 선택·안내 창·쓰기 차단) + 이 편만의 동작.
사용: python run_ep7.py check|make [작업폴더] [--fast] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 안전: 목록의 번호는 실제 사람 번호일 수 있다 → 확인 창의 [발송]은 누르지 않고 보여 주기만, [취소]로 닫는다.
  그래도 초대 화면의 쓰기 요청은 모두 막는다(요청차단: /invitation).
- 흐림: 목록의 이름(사진 옆)·생년월일·전화번호.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep3 as E3                                          # noqa: E402
from run_ep3 import maker, S, SceneError                      # noqa: E402

# 초대 목록: 전화번호·생년월일·사진 옆 이름을 흐리게
BLUR7 = r"""(() => {
  const phone = /\d{2,3}-\d{3,4}-\d{4}/, date = /\d{4}-\d{2}-\d{2}/;
  const run = () => {
    if (!/\/invitation\/send\/student/.test(location.pathname)) return;
    for (const e of document.querySelectorAll('p, span, div, td')) {
      if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
      const t = (e.innerText || '').trim();
      if (!t) continue;
      let hit = phone.test(t) || date.test(t);
      if (!hit && /^[가-힣]{2,4}$/.test(t)) {
        for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
          if (p.querySelector('img') && !p.closest('nav, aside, .MuiDrawer-root')) { hit = true; break; }
      }
      if (hit) e.classList.add('__tm_blur');
    }
  };
  setInterval(run, 120);
})()"""


class Ep7Recorder(E3.Ep3Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR7)
        super().scenario()

    def run_scene(self, s, last):
        if s.key == "P1":
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super(E3.Ep3Recorder, self).run_scene(s, last)

    def go_click(self, b, move=0.6):
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, move)
        self.sleep(0.1)
        self.click()

    def box_of(self, loc):
        b = loc.bounding_box()
        if not b:
            raise SceneError(self.scene, self.scene.label, "누를 곳을 찾지 못했어요")
        return b

    def holder(self, text, min_w=200, min_h=60):
        """글자를 품은 상자(카드·안내 상자)."""
        return self.pg.evaluate("""([w, mw, mh]) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim().startsWith(w) && e.getBoundingClientRect().width>0);
            if (!t) return null; let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>mw && r.height>mh) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; }
            const r=t.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", [text, min_w, min_h])

    def union(self, *bs, pad=8):
        x0 = min(b["x"] for b in bs); y0 = min(b["y"] for b in bs)
        x1 = max(b["x"] + b["width"] for b in bs); y1 = max(b["y"] + b["height"] for b in bs)
        return self.rect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)

    # ── 1단계 ──
    def do_P1(self, s, end):
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("수련생, 학부모(가족) 초대")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/invitation/send", timeout=20000)
        self.pg.get_by_text("지금 초대하기").first.wait_for(timeout=20000)
        self.sleep(0.4)

    def do_P2(self, s, end):                       # 두 카드
        a = self.holder("수련생 & 학부모", 250, 180)
        b = self.holder("관장 & 사범", 250, 180)
        s0 = self.now()
        self.glide(a["x"] + a["width"] / 2, a["y"] + a["height"] + 30, 0.8)
        self.spot(a, s0, s0 + max(1.5, self.dur[s.key] * 0.45), 8)
        self.sleep(max(1.2, self.dur[s.key] * 0.45))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] + 30, 0.8)
        self.spot(b, self.now() - 0.6, end + 0.2, 8)

    def do_P3(self, s, end):                       # 7일 자동 삭제 안내
        b = self.holder("초대장은 7일 후", 300, 80)
        s0 = self.now()
        self.glide(b["x"] + b["width"] - 40, b["y"] + b["height"] / 2, 0.8)
        self.spot(b, s0, end + 0.2, 8)

    def do_P4(self, s, end):                       # 수련생 & 학부모 → 지금 초대하기 → 가이드 닫기(두 번 뜰 수 있음)
        pg = self.pg
        btn = pg.get_by_text("지금 초대하기").first
        b = self.box_of(btn)
        s0 = self.now()
        self.spot(b, s0, s0 + 1.6, 8)
        self.go_click(b, 0.8)
        pg.wait_for_url("**/invitation/send/student**", timeout=20000)
        pg.get_by_text("초대 하기 사용 가이드").first.wait_for(timeout=20000)
        self.sleep(0.8)
        for _ in range(4):
            if not pg.locator(".MuiModal-root").count():
                break
            close = pg.get_by_text("닫기", exact=True).last
            self.go_click(self.box_of(close), 0.5)
            self.sleep(0.7)
        if pg.locator(".MuiModal-root").count():
            raise SceneError(s, "사용 가이드", "사용 가이드 창이 닫히지 않았어요")

    # ── 2단계 ──
    def do_S1(self, s, end):                       # 꼭 한번 읽어주세요(1·2번)
        b = self.holder("※ 꼭 한번 읽어주세요", 600, 120)
        s0 = self.now()
        self.glide(b["x"] + 520, b["y"] + 60, 0.8)
        self.glide(b["x"] + 520, b["y"] + b["height"] * 0.55, max(1.0, self.dur[s.key] * 0.5))
        self.spot(b, s0, end + 0.2, 6)

    def do_S2(self, s, end):                       # 초대 가능한 목록만 보기
        lab = self.pg.locator("label[for=available_list]").first
        b = self.box_of(lab)
        s0 = self.now()
        self.spot(self.rect(b["x"] - 34, b["y"] - 8, b["width"] + 44, b["height"] + 16), s0, end + 0.2, 0)
        self.sleep(max(0.4, self.dur[s.key] * 0.3))
        self.go_click(self.box_of(self.pg.locator("#available_list")) if self.pg.locator("#available_list").count() else b, 0.8)
        self.sleep(0.8)

    def rows(self):
        return self.pg.locator("input[type=checkbox]:not(#available_list)")

    def do_S3(self, s, end):                       # 한 줄 체크 + 참고 칸
        pg = self.pg
        cb = self.rows()
        if cb.count() < 2:
            raise SceneError(s, "초대할 사람", "초대할 수 있는 줄이 없어요")
        first = self.box_of(cb.nth(1))          # 0 은 머리줄 '전체'
        note = pg.get_by_text("초대 가능한 번호입니다.").first
        nb = self.box_of(note)
        s0 = self.now()
        row = self.rect(first["x"] - 12, first["y"] - 14, nb["x"] + nb["width"] - first["x"] + 30, first["height"] + 28)
        self.glide(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2, 0.8)
        self.sleep(0.1)
        self.click()
        self.spot(row, s0, s0 + max(1.6, self.dur[s.key] * 0.45), 0)
        self.sleep(max(1.0, self.dur[s.key] * 0.4))
        self.glide(nb["x"] + nb["width"] / 2, nb["y"] + nb["height"] + 18, 0.8)
        self.spot(self.rect(nb["x"] - 12, nb["y"] - 10, nb["width"] + 24, nb["height"] + 20), self.now() - 0.6, end + 0.2, 0)
        if self.mode == "dry" and not cb.nth(1).is_checked():
            raise SceneError(s, "초대할 사람", "체크가 되지 않았어요")

    # ── 3단계 ──
    def do_T1(self, s, end):                       # 초대장 발송 → 확인 창
        btn = self.pg.locator("button:has-text('초대장 발송')").first
        b = self.box_of(btn)
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.25))
        self.go_click(b, 0.9)
        self.spot(b, s0, end + 0.2, 8)
        self.pg.get_by_text("위 유의사항을 확인하였습니다").first.wait_for(timeout=10000)
        self.sleep(0.4)

    def do_T2(self, s, end):                       # 확인 창: 유의사항 체크, [발송]은 가리키기만(누르지 않음)
        pg = self.pg
        m = pg.locator(".MuiModal-root").filter(has_text="위 유의사항을 확인하였습니다").last
        mb = self.box_of(m.locator("div").filter(has_text="총 ").first) if m.locator("div").filter(has_text="총 ").count() else None
        dlg = self.holder("총 ", 300, 250) or mb
        agree = m.get_by_text("위 유의사항을 확인하였습니다").first
        send = m.locator("button:text-is('발송')").first
        s0 = self.now()
        if dlg:
            self.spot(dlg, s0, s0 + max(1.8, self.dur[s.key] * 0.4), 4)
        self.sleep(max(1.2, self.dur[s.key] * 0.3))
        ab = self.box_of(agree)
        self.go_click(self.rect(ab["x"] - 26, ab["y"], 20, ab["height"]), 0.7)   # 체크칸(글자 왼쪽)
        self.sleep(0.4)
        sb = self.box_of(send)
        self.glide(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2, 0.7)   # 가리키기만
        self.spot(sb, self.now() - 0.3, end + 0.2, 8)

    def do_T3(self, s, end):                       # [취소]로 닫고 → 초대장 · 조회
        pg = self.pg
        m = pg.locator(".MuiModal-root").filter(has_text="위 유의사항을 확인하였습니다").last
        cancel = m.locator("button:text-is('취소')").first
        self.go_click(self.box_of(cancel), 0.5)
        m.wait_for(state="detached", timeout=5000)
        self.sleep(0.3)
        top, it = self.side("초대장"), self.side("조회")
        if not (top and it):
            raise SceneError(s, "왼쪽 메뉴", "초대장·조회 메뉴를 찾지 못했어요")
        s0 = self.now()
        self.glide(top["x"] + 110, top["y"] + top["height"] / 2, 0.8)
        self.spot(top, s0, s0 + 1.4, 6)
        self.sleep(0.8)
        self.glide(it["x"] + 80, it["y"] + it["height"] / 2, 0.6)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)
        if self.mode == "dry" and any("invite" in x.lower() for x in self.log.get("blocked", [])):
            raise SceneError(s, "발송", "초대 요청이 나가려 했어요 — 확인 필요")


    # ── 학부모님 휴대폰(phone/phone.html) ──
    def phone(self, s, end, n):
        pg = self.pg
        if n == 1:
            pg.goto(PHONE, wait_until="load")
            pg.wait_for_timeout(1200)                 # 글꼴·그림
        pg.evaluate(f"show({n})")
        self.sleep(0.5)
        hot = self.box_of(pg.locator(f"#hot-{n}"))
        s0 = self.now()
        self.sleep(max(0.4, self.dur[s.key] * 0.2))
        self.glide(hot["x"] + hot["width"] * 0.6, hot["y"] + hot["height"] * 0.55, 0.8)
        if n == 2:
            self.sleep(0.2)
            self.click()                               # 수락 누르는 모습(그림 위라 아무 일도 없음)
        self.spot(self.rect(hot["x"] - 6, hot["y"] - 6, hot["width"] + 12, hot["height"] + 12), s0, end + 0.2, 0)

    def do_M1(self, s, end): self.phone(s, end, 1)
    def do_M2(self, s, end): self.phone(s, end, 2)
    def do_M3(self, s, end): self.phone(s, end, 3)
    def do_M4(self, s, end): self.phone(s, end, 4)

    def do_M5(self, s, end):                       # 완료 화면 그대로, 안내 문구만(다운로드 버튼 화면은 없음)
        hot = self.box_of(self.pg.locator("#hot-3"))
        s0 = self.now()
        self.glide(hot["x"] + hot["width"] * 0.5, hot["y"] + hot["height"] + 40, 0.8)
        self.spot(self.rect(hot["x"] - 6, hot["y"] - 6, hot["width"] + 12, hot["height"] + 12), s0, end + 0.2, 0)


PHONE = (HERE / "phone" / "phone.html").as_uri()
maker.Recorder = Ep7Recorder


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

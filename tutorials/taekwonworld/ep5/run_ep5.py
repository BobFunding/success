"""5편(사범님 초대, 반 배정) 만들기: 3편 녹화기(로그인·도장 선택·안내 창·쓰기 차단) + 이 편만의 동작.
사용: . ./.env.sh && python run_ep5.py check|make [작업폴더] [--fast] [--silent]
- 초대: 회원 유형 '사범' → 번호(흐림) → 초대장 보내기(invite_teacher_multi 차단: 문자 안 나감).
- 배정: 도장 관리 > 반 → 'A반 오후 2시' → 담당 추가 → 사범님 선택 → 추가(차단: 반 안 바뀜).
- 흐림: 반 정보 창·담당 추가 창의 사람 이름(사진 옆 2~4글자).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.resolve().parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep3"))
import run_ep3 as E3                                          # noqa: E402
from run_ep3 import maker, S, SceneError, E2                  # noqa: E402

CLASS = "A반 오후 2시"

# 반 화면의 창(반 정보·담당 추가) 안 사람 이름: 사진(또는 동그라미) 옆 2~4글자 한글
NAME_JS = r"""(() => {
  const run = () => {
    if (!/\/manage\/class/.test(location.pathname)) return;
    for (const m of document.querySelectorAll('.MuiModal-root')) {
      for (const e of m.querySelectorAll('p, span, div')) {
        if (e.childElementCount || e.classList.contains('__tm_blur')) continue;
        const t = (e.innerText || '').trim();
        if (!/^[가-힣]{2,4}$/.test(t) || ['전체 선택','담당 추가','담당 삭제','수련생 추가','시간표','반 정보','추가','저장','없음'].includes(t)) continue;
        for (let p = e.parentElement, i = 0; p && i < 3; p = p.parentElement, i++)
          if (p.querySelector('img, svg[data-testid*=Person], .MuiAvatar-root')) { e.classList.add('__tm_blur'); break; }
      }
    }
  };
  setInterval(run, 120);
})()"""


class Ep5Recorder(E3.Ep3Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(NAME_JS)
        super().scenario()

    def run_scene(self, s, last):
        if s.key == "P1":
            self.pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000)
            self.sleep(0.6)
        return super(E3.Ep3Recorder, self).run_scene(s, last)

    def guide_box(self, title):
        return self.pg.evaluate("""(w) => { const t=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0 && (e.innerText||'').trim()===w);
            let c=t; for(let i=0;i<8&&c;i++){ const r=c.getBoundingClientRect(); if (r.width>400 && r.height>250) return {x:r.x,y:r.y,width:r.width,height:r.height}; c=c.parentElement; } return null; }""", title)

    def close_guide(self, title, s, end, quick=False):
        close = self.pg.get_by_text("닫기", exact=True).last
        b = close.bounding_box()
        g = self.guide_box(title)
        s0 = self.now()
        if not quick:
            if g:
                self.spot(g, s0, s0 + max(1.0, self.dur[s.key] * 0.45), 6)
            self.sleep(max(0.5, self.dur[s.key] * 0.4))
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.6 if quick else 0.8)
        if not quick:
            self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now() - 0.8, end + 0.2, 4)
            self.wait_until(end - 0.3)
        else:
            self.sleep(0.15)
        self.click()
        self.pg.get_by_text(title).wait_for(state="hidden", timeout=8000)

    def do_P1(self, s, end):                       # 안내 창 → 사범님 초대, 반 배정
        dlg = self.dialog_box() or self.rect(742, 200, 436, 680)
        b = self.pill("사범님 초대, 반 배정")
        s0 = self.now()
        self.spot(dlg, s0, s0 + 1.6, 6)
        self.sleep(1.4)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.9)
        self.spot(b, s0 + 1.6, end + 0.2, 8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/invitation/send/teacher", timeout=20000)
        self.pg.get_by_text("초대 하기 사용 가이드").wait_for(timeout=20000)
        self.sleep(0.3)

    def do_P2(self, s, end):
        self.close_guide("초대 하기 사용 가이드", s, end)

    def do_V1(self, s, end):                       # 회원 유형: 사범
        sel = self.pg.locator(".MuiSelect-select").first.bounding_box()
        s0 = self.now()
        self.spot(self.rect(sel["x"] - 6, sel["y"] - 30, sel["width"] + 12, sel["height"] + 36), s0, end + 0.2, 4)
        self.go_click(sel, 0.8)
        self.sleep(0.5)
        opt = self.pg.locator("li[role=option]:text-is('사범')").bounding_box()
        self.go_click(opt, 0.5)
        self.sleep(0.3)
        if self.mode == "dry" and self.pg.locator("input[name='invite_list.0.recipient_type']").input_value() == "KW":
            raise SceneError(s, "회원 유형", "사범으로 바뀌지 않았어요")

    def go_click(self, b, move=0.6):
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, move)
        self.sleep(0.12)
        self.click()

    def do_V3(self, s, end):                       # 초대장 보내기(차단)
        btn = "button:has-text('초대장 보내기')"
        s0, b = self.approach(btn, end, frac=0.25)
        self.wait_until(min(end - 0.35, self.now() + 1.8))
        self.click()
        self.spot(b, s0, end, 8)
        self.sleep(0.6)
        if self.mode == "dry" and not any("invite" in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "초대장 보내기", "초대장 요청이 막히지 않았어요")

    def do_C1(self, s, end):                       # 도장 관리 → 반 (가이드 창은 빠르게 닫음)
        top = self.side("도장 관리")
        s0 = self.now()
        self.glide(top["x"] + 120, top["y"] + top["height"] / 2, 0.9)
        self.spot(top, s0, s0 + 1.6, 6)
        self.sleep(0.15)
        self.click()
        self.sleep(0.6)
        cls = self.side("반")
        if not cls:
            raise SceneError(s, "왼쪽 메뉴", "도장 관리 아래 '반'을 찾지 못했어요")
        self.glide(cls["x"] + 80, cls["y"] + cls["height"] / 2, 0.6)
        self.spot(cls, self.now() - 0.6, self.now() + 0.8, 6)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.wait_for_url("**/manage/class/list", timeout=20000)
        self.pg.get_by_text("반 사용 가이드").wait_for(timeout=20000)
        self.sleep(0.4)
        self.close_guide("반 사용 가이드", s, end, quick=True)

    def do_C2(self, s, end):                       # A반 오후 2시 줄
        row = self.pg.locator("div.flex.h-\\[60px\\]", has_text=CLASS).first
        b = row.bounding_box()
        s0 = self.now()
        self.spot(b, s0 + 0.5, end + 0.2, 4)
        self.glide(b["x"] + 160, b["y"] + b["height"] / 2, 0.9)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.get_by_text("담당 추가").first.wait_for(timeout=10000)
        self.sleep(0.5)

    def do_T1(self, s, end):                       # 담당 추가
        x, y, b = self.center("button:has-text('담당 추가')", s.label)
        head = self.pg.get_by_text("담당 사범님", exact=False).first.bounding_box()
        s0 = self.now()
        if head:
            self.spot(self.rect(head["x"] - 10, head["y"] - 10, b["x"] + b["width"] - head["x"] + 20, b["height"] + 20), s0, end + 0.2, 0)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(x, y, 0.8)
        self.wait_until(end - 0.3)
        self.click()
        self.pg.get_by_text("담당 사범님 추가").wait_for(timeout=10000)
        self.sleep(0.5)

    def do_T2(self, s, end):                       # 첫 번째 사범님 체크
        dlg = self.guide_box("담당 사범님 추가")
        cb = self.pg.locator(".MuiModal-root").filter(has_text="담당 사범님 추가").last.locator("input[type=checkbox]")
        n = cb.count()
        if n < 2:
            raise SceneError(s, "사범님", "고를 사범님이 없어요")
        first = cb.nth(1).bounding_box()             # 0 번은 '전체 선택'
        s0 = self.now()
        if dlg:
            self.spot(dlg, s0, s0 + max(1.2, self.dur[s.key] * 0.45), 4)
        self.sleep(max(0.6, self.dur[s.key] * 0.4))
        self.glide(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2, 0.8)
        row = self.rect(first["x"] - 14, first["y"] - 14, (dlg["x"] + dlg["width"] - first["x"] - 10) if dlg else 900, first["height"] + 28)
        self.spot(row, self.now() - 0.6, end + 0.2, 0)
        self.wait_until(end - 0.3)
        self.click()
        self.sleep(0.3)
        if self.mode == "dry" and not cb.nth(1).is_checked():
            raise SceneError(s, "사범님", "사범님이 선택되지 않았어요")

    def do_T3(self, s, end):                       # 추가(차단)
        btn = self.pg.locator("button:text-is('추가')").last
        b = btn.bounding_box()
        s0 = self.now()
        self.sleep(max(0.3, self.dur[s.key] * 0.2))
        self.go_click(b, 0.8)
        self.spot(b, s0, end, 8)
        self.sleep(0.6)
        if self.mode == "dry" and not any("taekwonworld.pe.kr" in x and "invite" not in x for x in self.log.get("blocked", [])):
            raise SceneError(s, "추가", "담당 추가 요청이 막히지 않았어요")


maker.Recorder = Ep5Recorder


def load():
    txt = (HERE / "scenario.yaml").read_text(encoding="utf-8").replace("{ID}", os.environ["TW_DEMO_ID"])
    import tempfile                       # 아이디가 들어간 사본은 저장소 밖(임시 폴더)에만 둔다
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

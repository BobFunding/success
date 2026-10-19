"""25편(내 정보) 만들기: 24편 녹화기(메뉴·글자 찾기·ghost 줌) + 이 편만의 동작.
사용: python run_ep25.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 저장·변경은 누르지 않고 가리키기만, 비밀번호 변경 창은 열어 보고 Esc 로 닫는다. 요청도 막는다(/mypage).
- 흐림: 프로필 창 이름, 이름·생년월일 칸, 아이디·이메일·전화번호, 자격증 번호(글자·입력칸 값).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
for d in ("ep24", "ep23", "ep22", "ep21", "ep20", "ep16"):
    sys.path.insert(0, str(HERE.parent / d))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep24 as E24                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

BLUR25 = r"""(() => {
  const secret = t => /@/.test(t) || /^0\d{8,11}$/.test(t) || /^0\d{1,2}-\d{3,4}-\d{4}$/.test(t) || /^[A-Z]{0,3}\d{6,}$/.test(t);
  const st = document.createElement('style');                // 다른 편 이름 규칙이 '로그아웃'·'관장님'까지 흐려서 되돌림
  st.textContent = '.__tm_blur.__tm_word { color: inherit !important; text-shadow: none !important; }';
  const addSt = () => { if (!st.isConnected && document.head) document.head.appendChild(st); };
  const run = () => {
    addSt();
    const leaves = [...document.querySelectorAll('div, span, p, td, h1, h2, h3, h4, h5, h6')].filter(e => !e.childElementCount);
    for (const e of leaves) {                                   // 프로필 창(≡): 사진 옆 이름
      const t = (e.innerText || '').trim();
      if (/^(로그아웃|관장님|사범님|내 정보)$/.test(t)) { e.classList.add('__tm_word'); continue; }
      if (!/^[가-힣]{2,4}$/.test(t) || e.classList.contains('__tm_blur')) continue;
      for (let p = e.parentElement, k = 0; p && k < 4; p = p.parentElement, k++)
        if (p.querySelector('img') && /로그아웃/.test(p.innerText || '')) { e.classList.add('__tm_blur'); break; }
    }
    if (!/\/mypage/.test(location.pathname)) return;
    for (const n of ['last_name', 'first_name']) for (const i of document.querySelectorAll(`input[name="${n}"]`)) i.classList.add('__tm_blur');
    for (const i of document.querySelectorAll('input[name="dob"]')) { const b = i.closest('.MuiInputBase-root') || i.parentElement; if (b) b.classList.add('__tm_blur'); }
    for (const i of document.querySelectorAll('input')) if (secret((i.value || '').trim())) i.classList.add('__tm_blur');
    for (const e of leaves) { const t = (e.innerText || '').trim(); if (t && secret(t)) e.classList.add('__tm_blur'); }
    const id = leaves.find(e => (e.innerText || '').trim() === 'ID');      // 'ID' 같은 줄 오른쪽 값
    if (id) { const a = id.getBoundingClientRect(), cy = a.y + a.height / 2;
      for (const v of leaves) { const b = v.getBoundingClientRect();
        if (v !== id && b.width > 0 && Math.abs(b.y + b.height / 2 - cy) < 14 && b.x > a.x + 40 && b.x < a.x + 500) v.classList.add('__tm_blur'); } }
  };
  setInterval(run, 80);
})()"""


class Ep25Recorder(E24.Ep24Recorder):
    def scenario(self) -> None:
        self.pg.add_init_script(BLUR25)
        super().scenario()

    def card_of(self, title, h=330):
        a = self.lab(title)
        return a, self.rect(a["x"] - 30, a["y"] - 40, 0, h)

    # ── 1단계 ──
    def do_P2(self, s, end):                       # ≡ 누르기 → 프로필 창
        self.glide(28, 25, 0.9)
        self.spot(self.rect(10, 8, 36, 34), self.now() - 0.3, self.now() + 1.6, 6)
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.click()
        self.nozoom()                              # 버튼 자리 대신 아래 look() 으로 프로필 창을 크게
        self.pg.get_by_text("내 정보", exact=True).first.wait_for(timeout=5000)
        self.look(self.rect(0, 0, 760, 420), end - self.now() + self.dur["P3"] * 0.7)
        self.sleep(0.4)
        pop = self.rect(16, 48, 236, 176)
        self.spot(pop, self.now(), end + 0.2, 6)
        self.wait_until(end - 0.1)

    def do_P3(self, s, end):                       # 내 정보
        pg = self.pg
        b = self.box_of(pg.get_by_text("내 정보", exact=True).first)
        self.spot(self.rect(b["x"] - 8, b["y"] - 6, b["width"] + 16, b["height"] + 12), self.now(), self.now() + 1.4, 4)
        self.sleep(max(0.3, self.dur[s.key] * 0.3))
        self.go_click(b, 0.7)
        pg.wait_for_url("**/mypage/account", timeout=20000)
        pg.get_by_text("계정 정보").first.wait_for(timeout=15000)
        self.sleep(0.8)

    # ── 2단계 ──
    def do_B1(self, s, end):
        a = self.lab("기본 정보")
        sv = self.box_of(self.pg.get_by_role("button", name="저장", exact=True).first)
        box = self.rect(a["x"] - 30, a["y"] - 40, sv["x"] + sv["width"] - a["x"] + 60, 330)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / 4.5)
        for w in ("사진 변경", "이름", "성별", "생년월일"):
            h = self.lab(w)
            self.glide(h["x"] + (60 if w == "사진 변경" else 260), h["y"] + h["height"] / 2, step * 0.6)
            self.sleep(step * 0.4)
        self.glide(sv["x"] + sv["width"] / 2, sv["y"] + sv["height"] / 2, step * 0.6)          # 저장(가리키기만)
        self.wait_until(end - 0.1)

    def do_B2(self, s, end):
        a = self.lab("계정 정보")
        box = self.rect(a["x"] - 30, a["y"] - 40, 784, 330)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / 3.5)
        for w in ("비밀번호 변경", "이메일 변경", "전화번호 변경"):
            h = self.lab(w)
            self.glide(h["x"] + 60, h["y"] + h["height"] / 2, step * 0.6)
            self.sleep(step * 0.4)
        self.wait_until(end - 0.1)

    def do_B3(self, s, end):                       # 비밀번호 변경 창 열기 → 보여 주기 → Esc
        pg = self.pg
        b = self.lab("비밀번호 변경")
        self.go_click(self.rect(b["x"], b["y"], b["width"], b["height"]), 0.7)
        self.nozoom()
        m = pg.locator(".MuiModal-root").filter(has_text="새 비밀번호").last
        m.wait_for(timeout=8000)
        self.sleep(0.5)
        box = self.box_of(m.locator(".MuiPaper-root, [role=dialog]").first) if m.locator(".MuiPaper-root, [role=dialog]").count() else None
        if box:
            self.spot(box, self.now(), end - 0.4, 4)
        for n in ("old_password", "new_password", "chk_password"):
            i = self.box_of(m.locator(f"input[name={n}]"))
            self.glide(i["x"] + 80, i["y"] + i["height"] / 2, 0.5)
            self.sleep(0.25)
        self.wait_until(end - 0.4)
        pg.keyboard.press("Escape")
        self.sleep(0.4)
        if pg.locator(".MuiModal-root").filter(has_text="새 비밀번호").count():     # Esc 가 안 먹으면 창 위 닫기 버튼
            x = self.box_of(m.locator("button.MuiIconButton-root").first)
            self.glide(x["x"] + x["width"] / 2, x["y"] + x["height"] / 2, 0.3)
            self.click()
            self.nozoom()
            self.sleep(0.5)
        if pg.locator(".MuiModal-root").filter(has_text="새 비밀번호").count():
            raise SceneError(s, "비밀번호 변경", "창이 닫히지 않았어요")

    # ── 3단계 ──
    def do_K1(self, s, end):
        a = self.lab("관장 정보")
        box = self.rect(a["x"] - 30, a["y"] - 46, 1620, 314)
        self.spot(box, self.now(), end + 0.2, 0)
        self.look(box, end - self.now())
        step = max(0.5, (self.dur[s.key] - 0.3) / 3.5)
        for w in ("단증/사범 자격증", "최종 학력", "도장 운영 경력"):
            h = self.lab(w)
            self.glide(h["x"] + 60, h["y"] + 70, step * 0.6)
            self.sleep(step * 0.4)
        self.wait_until(end - 0.1)

    def do_K2(self, s, end):                       # 더보기 → /mypage/resume → 천천히 내리기
        pg = self.pg
        b = self.box_of(pg.get_by_role("button", name="더보기").first)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now(), self.now() + 1.2, 6)
        self.go_click(b, 0.7)
        self.nozoom()
        pg.wait_for_url("**/mypage/resume", timeout=20000)
        pg.get_by_text("수상 이력").first.wait_for(timeout=15000)
        self.sleep(0.8)
        h = pg.evaluate("document.documentElement.scrollHeight")
        rest = max(1.0, end - self.now() - 0.3)
        if h > 1100:
            self.scroll_to(max(0, h - 1080) * 0.55, rest * 0.4)
            self.glide(900, 560, rest * 0.2)
            self.scroll_to(max(0, h - 1080), rest * 0.3)
        self.wait_until(end - 0.1)

    def do_K3(self, s, end):                       # 위로 → 저장(가리키기만)
        self.scroll_to(0, 0.6)
        self.sleep(0.2)
        b = self.box_of(self.pg.get_by_role("button", name="저장", exact=True).first)
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 0.8)
        self.spot(self.rect(b["x"] - 8, b["y"] - 8, b["width"] + 16, b["height"] + 16), self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.1)


maker.Recorder = Ep25Recorder


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
        nar = maker.narrate(sc, work)
        dur = {k: v[2] for k, v in nar.items()}
        from autoedit.tutorial import qa                     # 발음부터: 녹화 뒤에 문장을 고치면 다시 찍어야 하므로
        qa.pronunciation(sc, nar, work)
        print(maker.rehearse(sc, work, dur))
    else:
        print(quick.make(maker, sc, work, HERE))

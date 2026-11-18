"""읽기 전용: 영상 버튼 자리 안내용 화면 찍기. 쓰기 요청은 모두 막고, 앞 편들의 흐림 규칙을 그대로 넣는다."""
import os, sys, json
sys.path.insert(0, "/home/user/success"); T = "/home/user/success/tutorials/taekwonworld"
for d in ("ep25","ep24","ep23","ep22","ep21","ep20","ep16","ep15","ep2"): sys.path.insert(0, f"{T}/{d}")
sys.path.insert(0, T)
cwd = os.getcwd()
import run_ep2 as E2, run_ep15 as E15, run_ep16 as E16, run_ep20 as E20, run_ep21 as E21, run_ep22 as E22, run_ep25 as E25
os.chdir(cwd)
from autoedit.tutorial.recorder import style_script
from autoedit.tutorial import secrets as SEC
from playwright.sync_api import sync_playwright
INITS = [style_script(E2.EXTRA_CSS).replace("__priv", "__priv_ep2"), E2.BLUR_JS, E15.BLUR15, E16.BLUR16, E20.BLUR20, E21.BLUR21, E22.BLUR22, E25.BLUR25]
boxes = {}
def box(pg, loc):
    b = loc.bounding_box(); return [round(b["x"]), round(b["y"]), round(b["width"]), round(b["height"])]
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    ctx = br.new_context(viewport={"width": 1920, "height": 1080}, timezone_id="Asia/Seoul")
    for s in INITS: ctx.add_init_script(s)
    pg = ctx.new_page()
    st = {"in": False}
    def rt(r):
        q = r.request
        if st["in"] and q.method not in ("GET","HEAD","OPTIONS") and not any(k in q.url.lower().split("?")[0].rsplit("/",1)[-1] for k in ("read","list","search","info","get","detail","select")):
            return r.abort()
        r.continue_()
    pg.route("**/*", rt)
    pg.goto("https://taekwonworld.net/account/login", wait_until="networkidle"); pg.wait_for_timeout(1500)
    pg.fill("input[name=username]", os.environ["TW_DEMO_ID"]); pg.fill("input[name=password]", SEC.get("x")); pg.press("input[name=password]", "Enter")
    pg.wait_for_url(lambda u: "/account/login" not in u, timeout=30000)
    pg.goto("https://taekwonworld.net/dojang/select", wait_until="domcontentloaded"); pg.locator("div[slide]").first.wait_for(timeout=30000)
    pg.locator("div[slide]").filter(has=pg.locator("p", has_text="태권월드 태권도장")).first.get_by_text("관리하러 가기").click()
    pg.wait_for_url("**/home", timeout=30000); st["in"] = True
    pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000); pg.wait_for_timeout(1500)
    def close_all():
        for _ in range(4):
            if pg.locator(".MuiModal-root").count():
                c = pg.get_by_text("창 닫기", exact=True); d = pg.get_by_text("닫기", exact=True)
                (c.last.click() if c.count() else (d.last.click() if d.count() else pg.keyboard.press("Escape"))); pg.wait_for_timeout(800)
    close_all()
    def side(w):
        return pg.evaluate("""(w) => { const t=[...document.querySelectorAll('a, li, p, span, div')].filter(e=>(e.innerText||'').replace(/new/g,'').trim()===w && e.getBoundingClientRect().x<240 && e.getBoundingClientRect().width>0 && e.getBoundingClientRect().height<60).pop(); if(!t) return null; const r=t.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]; }""", w)
    def go(top, item):
        b = side(item)
        if not b:
            pg.get_by_text(top, exact=True).first.click(); pg.wait_for_timeout(800); b = side(item)
        pg.mouse.click(*b); pg.wait_for_timeout(4500)
    # ≡ 프로필 창 / ⋮ 등록된 도장 보기
    pg.mouse.click(28, 25); pg.wait_for_timeout(2500); pg.screenshot(path="p_menu.png"); pg.keyboard.press("Escape"); pg.mouse.click(1000, 1000); pg.wait_for_timeout(800)
    pg.mouse.click(207, 73); pg.wait_for_timeout(1200); pg.screenshot(path="p_dots.png"); pg.mouse.click(1000, 1000); pg.wait_for_timeout(800)
    # 대시보드(빈 칸)
    pg.mouse.click(*side("대시보드")); pg.wait_for_timeout(4500); close_all(); pg.screenshot(path="p_dash.png")
    # 일정: 저절로 뜨는 가이드 창 → 닫은 빈 달력
    go("앱", "일정"); pg.screenshot(path="p_sched_guide.png"); close_all(); pg.wait_for_timeout(800); pg.screenshot(path="p_sched.png")
    # 청구서 발행: 결제서비스 가입 전 화면
    go("납부", "청구서 발행"); pg.screenshot(path="p_bill_guide.png"); close_all(); pg.wait_for_timeout(800); pg.screenshot(path="p_bill.png")
    print("URL", pg.url)
    br.close()

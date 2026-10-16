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
    # 공개 화면
    pg.goto("https://taekwonworld.net/", wait_until="networkidle", timeout=60000); pg.wait_for_timeout(2500)
    pg.screenshot(path="main.png"); boxes["main"] = {"login": box(pg, pg.locator("button:has-text('로그인(관장)')").first)}
    pg.goto("https://taekwonworld.net/guide/kwanjang/class/regist", wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.screenshot(path="guide.png"); boxes["guide"] = {"h": box(pg, pg.get_by_text("반 등록하기", exact=True).first)}
    pg.goto("https://taekwonworld.net/account/login", wait_until="networkidle"); pg.wait_for_timeout(2000)
    pg.screenshot(path="login.png")
    boxes["login"] = {"join": box(pg, pg.get_by_text("회원가입", exact=True).last), "find": box(pg, pg.get_by_text("비밀번호 찾기", exact=True).first)}
    # 로그인 → 도장
    pg.fill("input[name=username]", os.environ["TW_DEMO_ID"]); pg.fill("input[name=password]", SEC.get("x")); pg.press("input[name=password]", "Enter")
    pg.wait_for_url(lambda u: "/account/login" not in u, timeout=30000)
    pg.goto("https://taekwonworld.net/dojang/select", wait_until="domcontentloaded"); pg.locator("div[slide]").first.wait_for(timeout=30000)
    pg.locator("div[slide]").filter(has=pg.locator("p", has_text="태권월드 태권도장")).first.get_by_text("관리하러 가기").click()
    pg.wait_for_url("**/home", timeout=30000); st["in"] = True
    pg.get_by_text("태권월드가 처음이신가요?").wait_for(timeout=30000); pg.wait_for_timeout(2500)
    pg.screenshot(path="home.png")
    m = pg.locator(".MuiModal-root").last
    t = pg.get_by_text("태권월드가 처음이신가요?").first
    boxes["home"] = {"modal": t.evaluate("""e => { let c=e; while (c && c.getBoundingClientRect().width < 380) c=c.parentElement; const r=c.getBoundingClientRect(); return [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]; }""")}
    for _ in range(4):
        if pg.locator(".MuiModal-root").count():
            c = pg.get_by_text("창 닫기", exact=True); (c.last.click() if c.count() else pg.keyboard.press("Escape")); pg.wait_for_timeout(700)
    # 반 관리: 사용 가이드 창 → 닫은 화면
    pg.goto("https://taekwonworld.net/manage/class/list", wait_until="domcontentloaded"); pg.get_by_text("반 사용 가이드").first.wait_for(timeout=20000); pg.wait_for_timeout(3000)
    pg.screenshot(path="classguide.png")
    t = pg.get_by_text("반 사용 가이드").first
    mb = t.evaluate("""e => { let c=e; while (c && c.getBoundingClientRect().width < 500) c=c.parentElement; const r=c.getBoundingClientRect(); return [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]; }""")
    boxes["classguide"] = {"modal": mb, "title": box(pg, t)}
    pg.get_by_text("닫기", exact=True).last.click(); pg.wait_for_timeout(1000)
    pg.screenshot(path="class.png")
    boxes["class"] = {"title": box(pg, pg.get_by_text("반 관리", exact=True).first), "link": box(pg, pg.get_by_text("사용 가이드", exact=True).first)}
    # 휴관 수련생 조회(부분부터 재생 예)
    pg.goto("https://taekwonworld.net/manage/student/list?class=0", wait_until="domcontentloaded"); pg.wait_for_timeout(3500)
    c = pg.get_by_text("닫기", exact=True)
    if c.count(): c.last.click(); pg.wait_for_timeout(1000)
    pg.wait_for_timeout(1500); pg.screenshot(path="rest.png")
    boxes["rest"] = {"title": box(pg, pg.get_by_text("수련생 조회", exact=True).first), "link": box(pg, pg.get_by_text("사용 가이드", exact=True).first)}
    br.close()
json.dump(boxes, open("boxes.json", "w"), ensure_ascii=False)
print(json.dumps(boxes, ensure_ascii=False))

"""6단계 검사: 로그인 편(2편 같은 영상)을 어떤 사이트에서든 만들 수 있는지 — 연습용 사이트로 처음부터 끝까지.

준비: python -m http.server 8765 -d tutorials/sample_site
실행: python tutorials/login_check/run_login.py

시연(사람 역할): 공지 닫기 → 사서 로그인(아이디·비밀번호) → '회원 관리' 메뉴에 마우스 올려 '회원 등록' →
이름·휴대전화·인증요청 → 인증번호 → 저장 → 완료 화면.
확인: 비밀번호 보관함에 저장, 보여 주기 장면 추가, 마지막 장면은 '확인받고 실제 실행'.
만들기: 녹화 중 인증번호를 물으면 답한다. 끝나면 '로그인한 상태에서 시작'으로 바꿔 빠른 미리보기.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "shots"
OUT.mkdir(exist_ok=True)
CHROME = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None
env = dict(os.environ, TUTORIAL_HEADLESS="1", TUTORIAL_DEMO_CDP="9333")
env.pop("TUTORIAL_SECRET", None)              # 보관함을 실제로 쓰게
srv = subprocess.Popen([sys.executable, "tutorial.py", "ui", "--no-browser", "--port", "8770"], cwd=ROOT, env=env)
time.sleep(2)


def shot(pg, name):
    pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("화면:", name, flush=True)


def human(demo):
    def move(loc):
        b = loc.bounding_box()
        demo.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=12)
        time.sleep(0.3)
        return b

    def click(loc):
        b = move(loc)
        demo.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)

    def typ(t):
        for ch in t:
            demo.keyboard.type(ch); time.sleep(0.05)
    time.sleep(0.8)
    click(demo.get_by_role("button", name="닫기"))
    click(demo.get_by_role("link", name="사서 로그인")); demo.wait_for_url("**/login.html"); time.sleep(0.4)
    click(demo.locator("#uid")); typ("librarian")
    click(demo.locator("#upw")); typ("book1234!")
    click(demo.get_by_role("button", name="로그인")); demo.wait_for_url("**/admin.html"); time.sleep(0.8)
    move(demo.get_by_role("link", name="회원 관리 ▾")); time.sleep(0.6)          # 메뉴 펼치기
    click(demo.get_by_role("link", name="회원 등록")); demo.wait_for_url("**/member-new.html"); time.sleep(0.4)
    click(demo.locator("#mname")); typ("김하늘")
    click(demo.locator("#mphone")); typ("01012345678")
    click(demo.get_by_role("button", name="인증요청")); time.sleep(0.5)
    click(demo.locator("#mcode")); typ("482913")
    click(demo.get_by_role("button", name="저장")); demo.wait_for_url("**/member-done.html"); time.sleep(0.5)


try:
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=CHROME)
        pg = br.new_page(viewport={"width": 1280, "height": 900})
        pg.on("dialog", lambda d: d.accept())       # '실제로 실행할까요?' 확인 → 예(연습용 사이트)
        pg.goto("http://127.0.0.1:8770/")
        pg.evaluate("localStorage.setItem('tipDone','true')")
        pg.reload(); pg.wait_for_selector("#url")
        pg.fill("#url", "http://localhost:8765/index.html")
        pg.fill("#ttl", "사서 로그인하고 회원 등록하기")
        pg.click("#demoGo"); pg.wait_for_selector("text=기록 중")
        demo = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0].pages[0]
        human(demo)
        time.sleep(1.2)
        pg.click("#stop")
        pg.wait_for_selector("text=이렇게 말하고, 이렇게 누릅니다", timeout=60000)
        shot(pg, "1_확인_시연직후")
        # 비밀번호를 보관함에 한 번
        if pg.locator("input[data-secret]").count():          # 이미 저장했으면 다시 묻지 않음
            pg.fill("input[data-secret]", "book1234!")
            pg.click("[data-secret-save]")
        pg.wait_for_selector("text=✓ 저장됨")
        # 보여 주기 장면: 로그인 버튼 뒤(대시보드)
        rows = pg.locator("tbody tr")
        idx = next(i for i in range(rows.count()) if "로그인" in rows.nth(i).inner_text() and "클릭" in rows.nth(i).inner_text()
                   and "사서" not in rows.nth(i).inner_text())
        pg.select_option("#shAfter", str(idx))
        pg.fill("#shTgt", "오늘 할 일"); pg.fill("#shSay", "로그인하면 오늘 할 일이 먼저 보여요.")
        pg.click("#shAdd")
        # 마지막 장면: 확인받고 실제 실행
        pg.click("#doneOpt"); pg.check("input[name=dn][value=real]")
        pg.click("#reh"); pg.wait_for_selector("text=리허설 통과", timeout=600000)
        shot(pg, "2_확인_리허설")
        pg.click("#next"); pg.wait_for_selector("text=만들기 전에 골라 주세요")
        t0 = time.time()
        pg.click("#next")                                   # 만들기 → (확인 창: 실제 실행)
        pg.wait_for_selector("#ansV", timeout=1800000)      # 녹화 중 질문
        time.sleep(1)
        shot(pg, "3_만들기_질문")
        pg.fill("#ansV", "482913"); pg.click("#ansGo")
        pg.wait_for_selector("#next:not([disabled])", timeout=3600000)
        print(f"만들기 {time.time() - t0:.0f}초", flush=True)
        shot(pg, "4_만들기_끝_검수")
        pg.click("#next"); pg.wait_for_selector("video"); time.sleep(1)
        shot(pg, "5_결과")
        # 로그인한 상태에서 시작으로 바꿔 빠른 미리보기
        pg.locator(".step").nth(1).click(); pg.wait_for_selector("text=이렇게 말하고")
        pg.check("input[name=st][value=로그인]"); pg.wait_for_selector("text=미리 해 둬요")
        shot(pg, "6_확인_로그인상태")
        pg.click("#next"); pg.wait_for_selector("text=만들기 전에 골라 주세요")
        pg.click("#quick")
        pg.wait_for_selector("#ansV", timeout=1800000)
        pg.fill("#ansV", "482913"); pg.click("#ansGo")
        pg.wait_for_selector("#final", timeout=3600000)
        shot(pg, "7_미리보기_로그인상태")
        br.close()
finally:
    srv.terminate()

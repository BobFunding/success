"""4단계 검사: 화면(UI)을 시안과 같은 흐름으로 처음부터 끝까지 눌러 본다. 단계마다 화면 사진을 남긴다.

준비: python -m http.server 8765 -d tutorials/sample_site   (연습용 사이트)
실행: python tutorials/ui_check/run_ui.py
- 화면 서버를 띄우고(창 없는 브라우저, 시연 브라우저는 바깥에서 조작할 수 있게 9333 포트),
- 사람 역할: 화면 버튼을 누르고, 시연 브라우저에서 사람처럼 회원가입을 한 번 한다.
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
env = dict(os.environ, TUTORIAL_HEADLESS="1", TUTORIAL_DEMO_CDP="9333", TUTORIAL_SECRET="book1234!")
srv = subprocess.Popen([sys.executable, "tutorial.py", "ui", "--no-browser", "--port", "8770"], cwd=ROOT, env=env)
time.sleep(2)


def shot(pg, name):
    pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("화면:", name)


def human(demo):
    """시연 브라우저에서 사람처럼: 한 번 둘러보고, 회원가입."""
    def click(loc):
        b = loc.bounding_box()
        demo.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=10)
        time.sleep(0.3)
        demo.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)

    def typ(t):
        for ch in t:
            demo.keyboard.type(ch); time.sleep(0.06)
    time.sleep(0.8)
    click(demo.get_by_role("button", name="닫기"))           # 공지 팝업 닫기(장면에서 빠져야 함)
    click(demo.get_by_role("link", name="회원가입 하기")); demo.wait_for_url("**/join.html"); time.sleep(0.4)
    click(demo.locator("#name")); typ("홍길동")
    click(demo.locator("#email")); typ("reader@example.com")
    click(demo.get_by_role("button", name="중복 확인"))
    click(demo.locator("#pw")); typ("book1234!")
    click(demo.locator("#pw2")); typ("book1234!")
    demo.locator("#topic").select_option(label="과학"); time.sleep(0.3)
    click(demo.locator("label.agree"))
    click(demo.get_by_role("button", name="가입하기")); demo.wait_for_url("**/done.html"); time.sleep(0.4)


try:
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=CHROME)
        pg = br.new_page(viewport={"width": 1280, "height": 900})
        pg.goto("http://127.0.0.1:8770/")
        pg.wait_for_selector("text=어떤 사이트의 사용법을 만들까요?")
        shot(pg, "1_시작")
        pg.fill("#url", "http://localhost:8765/index.html")
        pg.fill("#ttl", "도서관 회원가입")
        pg.click("#demoGo")
        pg.wait_for_selector("text=기록 중")
        cdp = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        demo = cdp.contexts[0].pages[0]
        human(demo)
        time.sleep(1.2)
        shot(pg, "1b_기록중")
        pg.click("#stop")
        pg.wait_for_selector("text=이렇게 말하고, 이렇게 누릅니다", timeout=60000)
        shot(pg, "2_확인")
        # 문장 하나 고치기
        el = pg.locator("[data-say='1']")
        el.click(); pg.keyboard.press("End"); pg.keyboard.type(" 실명이 아니어도 돼요.")
        pg.click("#reh")
        pg.wait_for_selector("text=리허설 통과", timeout=300000)
        shot(pg, "2b_리허설")
        # ⚙ 설정
        pg.click("#settingsBtn"); pg.wait_for_selector("#saveBrand"); time.sleep(0.5)
        shot(pg, "3a_설정_브랜드")
        pg.check("#tbR"); time.sleep(0.3)
        shot(pg, "3b_설정_규칙")
        pg.click("#closeDrawer")
        pg.click("#next")
        pg.wait_for_selector("text=만들기 전에 골라 주세요")
        pg.click("[data-play='현수 · 차분']")
        pg.wait_for_function("document.querySelector('#aud') && document.querySelector('#aud').src.includes('preview')", timeout=60000)
        shot(pg, "3_선택")
        t0 = time.time()
        pg.click("#quick")                                   # 빠른 미리보기 먼저
        pg.wait_for_selector("text=남았어요", timeout=120000)
        time.sleep(3)
        shot(pg, "4_만들기")
        pg.wait_for_selector("#final", timeout=3600000)
        print(f"빠른 미리보기 {time.time() - t0:.0f}초")
        shot(pg, "4a_미리보기")
        t0 = time.time()
        pg.click("#final")                                   # 녹화를 다시 쓰는 최종본
        pg.wait_for_selector("#next:not([disabled])", timeout=3600000)
        print(f"최종본 {time.time() - t0:.0f}초")
        shot(pg, "4b_다만듦")
        pg.click("#next")
        pg.wait_for_selector("video")
        time.sleep(1)                     # 검사용 Chromium 은 H.264 를 못 틀어 표지만 보임(사용자 브라우저는 재생)
        shot(pg, "5_결과")
        # 휴대폰 폭
        pg.set_viewport_size({"width": 390, "height": 844}); time.sleep(0.4)
        shot(pg, "6_휴대폰폭")
        br.close()
finally:
    srv.terminate()

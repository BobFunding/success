"""3단계 검사: 연습용 사이트에서 '한 번 해 보이기'를 사람처럼 흉내 내고(실수·머뭇거림 포함) 장면 표를 만든다.
그다음 `python tutorial.py make tutorials/demo_check/scenario.yaml` 로 영상까지 만든다.

먼저 사이트 띄우기: python -m http.server 8765 -d tutorials/sample_site
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from autoedit.tutorial.demo_record import DemoSession, save  # noqa: E402

URL = "http://localhost:8765/index.html"
here = Path(__file__).parent


def human_click(pg, loc, pause=0.4):
    b = loc.bounding_box()
    pg.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=12)
    time.sleep(pause)
    pg.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def human_type(pg, text, delay=0.08):
    for ch in text:
        pg.keyboard.type(ch)
        time.sleep(delay)


s = DemoSession(URL, headless=True)
pg = s.page
time.sleep(0.8)                                            # 화면 둘러보기(머뭇거림)
human_click(pg, pg.get_by_role("button", name="닫기"))      # 공지 팝업 닫기(장면에서 빠져야 함)
human_click(pg, pg.get_by_role("link", name="자료 검색").first)   # 실수: 다른 메뉴
pg.wait_for_load_state("networkidle"); time.sleep(0.6)
pg.go_back(); pg.wait_for_load_state("networkidle"); time.sleep(0.5)   # 뒤로 가기
human_click(pg, pg.get_by_role("button", name="오늘 하루 보지 않기"))   # 팝업이 다시 떠서 이번엔 하루 닫기
pg.mouse.click(300, 700)                                    # 빈 곳 누르기
human_click(pg, pg.get_by_role("link", name="회원가입 하기"))
pg.wait_for_url("**/join.html"); time.sleep(0.5)
human_click(pg, pg.locator("#name")); human_type(pg, "홍길도"); pg.keyboard.press("Backspace"); human_type(pg, "동")  # 오타 고치기
human_click(pg, pg.locator("#email")); human_type(pg, "reader@example.com")
human_click(pg, pg.get_by_role("button", name="중복 확인"))
human_click(pg, pg.locator("#pw")); human_type(pg, "book1234!")
human_click(pg, pg.locator("#pw2")); human_type(pg, "book1234!")
pg.locator("#topic").select_option(label="과학"); time.sleep(0.4)
lab = pg.locator("label.agree")
human_click(pg, lab); human_click(pg, lab, 0.2); human_click(pg, lab)    # 켰다 껐다 켬
human_click(pg, pg.get_by_role("button", name="가입하기"))
pg.wait_for_url("**/done.html"); time.sleep(0.5)
sc = s.finish(topic="도서관 회원가입", brand="basic", next_topic="책 빌리기")
print(save(sc, here / "scenario.yaml"))
print(len(s.events), "개 동작 기록 →", len(sc["장면"]), "장면")

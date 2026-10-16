"""19편(대시보드) 만들기: 16편 녹화기(메뉴·창 닫기 nozoom) + 이 편만의 동작.
사용: python run_ep19.py check|make [작업폴더] [--silent]   (TW_DEMO_ID 환경변수, 비밀번호는 보관함)
- 대시보드는 읽기만 하는 화면. 대시보드 읽기 요청(dojang_home_*)은 POST 라 통과시키고, 그 밖의 쓰기는 막는다.
- 데모 도장의 이달 납부율·반 출석이 비어 있어, 녹화 브라우저 안에서만 읽기 응답에 예시 숫자를 넣는다(서버 저장 없음).
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 맨 위
sys.path.insert(0, str(HERE.parent / "ep16"))
sys.path.insert(0, str(HERE.parent))
import quick                                                  # noqa: E402
import run_ep16 as E16                                        # noqa: E402
from run_ep16 import maker, S, SceneError                     # noqa: E402

BILL = {"paid_count": 11, "non_paid_count": 4}               # 예시: 15명 중 11명 납부
ATTEND = {"A반 오후 2시": (4, 1, 3, 1), "A반 오후 3시": (1, 0, 1, 0), "B반 오후 2시": (2, 0, 1, 1)}   # 반: (어제 출석, 어제 결석, 오늘 출석, 오늘 결석)


class Ep19Recorder(E16.Ep16Recorder):
    def block_requests(self) -> None:
        if self.blocking:
            return
        pg = self.pg

        def guard(r):
            q = r.request
            api = "taekwonworld" in q.url and q.resource_type in ("xhr", "fetch")
            if api and "dojang_home_billRate" in q.url:
                res = r.fetch()
                r.fulfill(response=res, body=json.dumps(BILL), content_type="application/json")
                self.log.setdefault("faked", []).append("billRate")
                return
            if api and "dojang_home_class" in q.url:
                res = r.fetch()
                d = res.json()
                for row in d.get("data", []):
                    a = ATTEND.get(row.get("title"))
                    if a:
                        row.update(yesterday_count=a[0], yesterday_absent_count=a[1], today_count=a[2], today_absent_count=a[3])
                r.fulfill(response=res, body=json.dumps(d, ensure_ascii=False), content_type="application/json")
                self.log.setdefault("faked", []).append("class")
                return
            write = q.method not in ("GET", "HEAD", "OPTIONS")
            reading = "read" in q.url.lower() or "dojang_home" in q.url
            if api and write and self.blocked(pg.url or "") and not reading:
                self.log.setdefault("blocked", []).append(f"{q.method} {q.url[:80]}")
                r.abort()
                return
            r.continue_()
        pg.route("**/*", guard)
        self.blocking = True

    def look(self, b, hold):
        """누르지 않고 b 자리로 줌(클릭 효과 없음): 표·그래프를 크게 보여 줄 때."""
        from autoedit.tutorial.recorder import SCALE
        z = max(1.0, min(1.8, 0.85 * 1920 / (b["width"] + 40), 0.85 * 1080 / (b["height"] + 40)))
        self.log["clicks"].append({"t": round(self.now(), 3), "x": (b["x"] + b["width"] / 2) * SCALE,
                                   "y": (b["y"] + b["height"] / 2) * SCALE, "ghost": True, "hold": round(hold, 2), "zoom": round(z, 2)})

    def panel(self, title, mw=400, mh=200):
        b = self.holder_box(title, mw, mh)
        if not b:
            raise SceneError(self.scene, title, "화면에서 찾지 못했어요")
        return b

    def show_panels(self, s, end, titles, mw=300, mh=150):
        boxes = [self.panel(t, mw, mh) for t in titles]
        u = boxes[0]
        for b in boxes[1:]:
            u = self.union(u, b)
        self.spot(self.rect(u["x"] - 6, u["y"] - 6, u["width"] + 12, u["height"] + 12), self.now(), end + 0.2, 0)
        self.look(u, end - self.now() - 0.3)
        for b in boxes:
            self.glide(b["x"] + b["width"] * 0.4, b["y"] + 40, max(0.6, self.dur[s.key] / (len(boxes) + 1)))
            self.sleep(0.2)

    # ── 1단계: 첫 화면에서 오늘 보기 ──
    def do_H1(self, s, end):
        self.show_panels(s, end, ["오늘의 출결 현황", "초대장 발송 현황", "차량 현황"], 250, 80)

    def do_H2(self, s, end):
        self.show_panels(s, end, ["수련비 납부 현황", "2026년 10월 일정"], 250, 80)

    # ── 2단계: 대시보드로 흐름 보기 ──
    def do_P2(self, s, end):
        pg = self.pg
        it = self.side("대시보드")
        self.sleep(max(0.4, self.dur[s.key] * 0.35))
        self.glide(it["x"] + 90, it["y"] + it["height"] / 2, 0.8)
        self.spot(it, self.now() - 0.4, end + 0.2, 6)
        self.wait_until(end - 0.3)
        self.click()
        pg.wait_for_url("**/dashboard", timeout=20000)
        pg.get_by_text("반 정보").first.wait_for(timeout=15000)
        self.sleep(1.0)

    def one(self, s, end, title, mw=500, mh=300):
        b = self.panel(title, mw, mh)
        self.spot(self.rect(b["x"] - 6, b["y"] - 6, b["width"] + 12, b["height"] + 12), self.now(), end + 0.2, 0)
        self.look(b, end - self.now() - 0.3)
        self.glide(b["x"] + 120, b["y"] + 40, 0.8)
        self.sleep(max(0.6, self.dur[s.key] * 0.3))
        self.glide(b["x"] + b["width"] * 0.7, b["y"] + b["height"] * 0.55, max(0.8, self.dur[s.key] * 0.3))

    def do_D1(self, s, end): self.one(s, end, "월별 소속 수련생 수")
    def do_D2(self, s, end): self.one(s, end, "급/품/단 수련생 통계")
    def do_D3(self, s, end): self.one(s, end, "2026년 10월 수련비 납부율", 400, 300)
    def do_D4(self, s, end): self.one(s, end, "반 정보")

    def do_D5(self, s, end):                       # 왼쪽 메뉴 훑기
        pg = self.pg
        a, z = self.side("수련생"), self.side("도장 홈페이지")
        if not (a and z):
            raise SceneError(s, "왼쪽 메뉴", "메뉴를 찾지 못했어요")
        self.spot(self.rect(0, a["y"] - 8, 232, z["y"] + z["height"] + 16 - a["y"]), self.now(), end + 0.2, 0)
        self.glide(110, a["y"] + a["height"] / 2, 0.8)
        self.glide(110, z["y"] + z["height"] / 2, max(1.2, self.dur[s.key] * 0.5))


maker.Recorder = Ep19Recorder


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

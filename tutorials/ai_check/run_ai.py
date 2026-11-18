"""8단계 검사: 'AI에게 맡기기'의 둘레(누를 곳 목록 → 실제 마우스·키보드 → 기록 → 장면 표, 저장 차단, 비밀번호 질문·보관함)를
실제 브라우저로 확인한다. 이 환경에는 Claude 키가 없어서, AI 자리에는 정해진 순서로 답하는 대역(ScriptedLLM)을 쓴다.
(실제 Claude 가 순서를 고르는 부분은 키가 있는 PC 에서 따로 확인)

준비: python -m http.server 8765 -d tutorials/sample_site
실행: python tutorials/ai_check/run_ai.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from autoedit.tutorial import assistant as A          # noqa: E402
from autoedit.tutorial import secrets as SEC           # noqa: E402

PLAN = [("click", "닫기", ""), ("click", "사서 로그인", ""), ("type", "uid", "librarian"), ("secret", "upw", "비밀번호를 알려 주세요"),
        ("click", "로그인", ""), ("hover", "회원 관리", ""), ("click", "회원 등록", ""), ("type", "mname", "김하늘"),
        ("type", "mphone", "01012345678"), ("click", "인증요청", ""), ("secret", "mcode", "문자로 온 인증번호를 알려 주세요"),
        ("click", "저장", ""), ("done", "", "회원 등록까지 함")]


class ScriptedLLM:
    available = True

    def __init__(self):
        self.i = 0
        self.seen = []

    def parse(self, system, content, schema, effort="medium", max_tokens=0):
        text = content[1]["text"]
        listing = re.findall(r"^\[(\d+)\] (\S+) '([^']*)'", text, re.M)
        self.seen.append(len(listing))
        kind, want, val = PLAN[self.i]
        self.i += 1
        if kind == "done":
            return schema(kind="done", text=val)
        idx = None
        for n, tag, name in listing:
            if name == want or (want in name and kind != "type"):
                idx = int(n); break
        if idx is None:                     # 칸은 이름 대신 순서로(uid → 첫 글자 칸 등) — 라벨로 다시 찾기
            labels = {"uid": "아이디", "upw": "비밀번호", "mname": "이름", "mphone": "휴대전화", "mcode": "인증번호"}
            for n, tag, name in listing:
                if labels.get(want, "~") in name:
                    idx = int(n); break
        if kind == "secret":
            return schema(kind="type", index=idx, text=val, secret=True)
        return schema(kind=kind, index=idx, text=val, reason=f"{want}")


asked = []


def ask(q, shot):
    asked.append((q, bool(shot)))
    return "book1234!" if "비밀번호" in q else "482913"


if __name__ == "__main__":
    SEC.STORE = Path(__file__).parent / "_secrets_test.json"     # 실제 보관함을 건드리지 않음
    SEC._kr = lambda: None
    llm = ScriptedLLM()
    r = A.explore(llm, "http://localhost:8765/index.html", "사서 로그인하고 회원 등록하기", ask=ask, log=print)
    sc = r["scenario"]
    out = Path(__file__).parent / "scenario_ai.yaml"
    from autoedit.tutorial.demo_record import save
    save(sc, out)
    vals = [f.get("값") for s in sc.get("미리하기", []) + sc["장면"] for f in (s.get("칸") or [])]
    report = {"마지막주소": r["last_url"], "조작": r["steps"], "누를곳목록": llm.seen, "질문": asked, "장면수": len(sc["장면"]),
              "장면": [(s.get("동작"), s.get("대상"), s.get("말")) for s in sc["장면"]], "칸값": vals,
              "보관함열쇠": sorted(SEC._file())}
    (Path(__file__).parent / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    SEC.STORE.unlink(missing_ok=True)

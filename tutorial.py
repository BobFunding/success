"""튜토리얼 메이커 명령행 (화면은 4단계에서).

python tutorial.py make tutorials/ep1/scenario.yaml              # 처음부터 끝까지
python tutorial.py make tutorials/ep1/scenario.yaml --only 편집  # 일부 단계만 (목소리, 리허설, 녹화, 편집)
python tutorial.py check tutorials/ep1/scenario.yaml             # 장면 표 검사 + 리허설
python tutorial.py demo https://example.com --topic "회원가입"   # 한 번 해 보이기 → 장면 표
python tutorial.py repro                                         # 1편 재현 검사
"""
import argparse
import sys
from pathlib import Path

from autoedit.tutorial import maker, scenario


def main() -> int:
    ap = argparse.ArgumentParser(description="웹사이트 사용법 영상 만들기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="만들기")
    m.add_argument("scenario")
    m.add_argument("--work", help="작업 폴더 (기본: output/tutorial/<파일이름>)")
    m.add_argument("--only", nargs="+", choices=maker.STAGES, help="이 단계만")
    m.add_argument("--fast", action="store_true", help="1080p 사본 생략")
    c = sub.add_parser("check", help="장면 표 검사 + 리허설")
    c.add_argument("scenario")
    c.add_argument("--work")
    d = sub.add_parser("demo", help="한 번 해 보이기: 브라우저에서 한 번 하면 장면 표를 만든다")
    d.add_argument("url")
    d.add_argument("--topic", default="", help="영상 주제 (비우면 자동)")
    d.add_argument("--brand", default="", help="브랜드 이름 (presets/brands)")
    d.add_argument("--tone", default="차분", choices=("차분", "친근", "전문"))
    d.add_argument("--next", default="", help="다음 편 주제")
    d.add_argument("--out", default="", help="장면 표 파일 (기본: output/tutorial/<주제>/scenario.yaml)")
    r = sub.add_parser("repro", help="1편 재현 검사")
    r.add_argument("--work", default="output/repro")
    r.add_argument("--only", nargs="+", choices=("기준", "같은녹화", "프로그램", "비교"))
    a = ap.parse_args()

    if a.cmd == "demo":
        from autoedit.tutorial.demo_record import DemoSession, save
        sess = DemoSession(a.url)
        input("뜬 브라우저에서 평소처럼 한 번 해 보세요. 화면은 찍지 않고 동작만 기록해요.\n다 하셨으면 여기서 Enter 를 눌러 주세요(■ 끝). ")
        try:
            sc = sess.finish(topic=a.topic, brand=a.brand, tone=a.tone, next_topic=a.next)
        except ValueError as e:
            print(e)
            return 1
        out = Path(a.out or f"output/tutorial/{sc['파일이름']}/scenario.yaml")
        save(sc, out)
        print(f"장면 {len(sc['장면'])}개를 만들었어요: {out}\n'말'을 다듬은 뒤: python tutorial.py make {out}")
        return 0
    if a.cmd == "repro":
        from autoedit.tutorial import repro
        return 0 if repro.main(Path(a.work), a.only) else 1
    try:
        sc = scenario.load(a.scenario)
    except scenario.ScenarioError as e:
        print(f"장면 표 오류: {e}")
        return 1
    work = Path(a.work or f"output/tutorial/{sc.file_name}")
    from autoedit.tutorial.capture import CaptureUnavailable
    from autoedit.tutorial.recorder import SceneError
    try:
        if a.cmd == "check":
            maker.make(sc, work, stages=("목소리", "리허설"))
            print("리허설 통과: 모든 누를 곳을 찾았어요.")
            return 0
        res = maker.make(sc, work, stages=a.only or maker.STAGES, fast=a.fast)
    except (SceneError, CaptureUnavailable) as e:      # 사람 말로, 그 자리에
        print(f"멈췄어요: {e}")
        return 1
    if res:
        print(f"완성: {res['final']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

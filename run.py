"""명령줄 실행.

  python run.py 영상.mp4
  python run.py 영상.mp4 --no-illust --allow "홍길동,내채널"
  python run.py --rerender output/영상_20261005_120000     # edit_plan.json 수정 후 최종본만 다시
"""
import argparse
from pathlib import Path

from autoedit.config import Settings
from autoedit.pipeline import render_from_plan, run


def main() -> None:
    p = argparse.ArgumentParser(description="유튜브 영상 자동 편집기")
    p.add_argument("video", nargs="?", help="편집할 영상 파일")
    p.add_argument("--rerender", metavar="WORK_DIR", help="edit_plan.json 기준으로 최종본만 다시 렌더링")
    p.add_argument("--no-cut", action="store_true", help="컷 편집 끄기")
    p.add_argument("--no-illust", action="store_true", help="설명 일러스트 끄기")
    p.add_argument("--no-privacy", action="store_true", help="개인정보 처리 끄기")
    p.add_argument("--no-review", action="store_true", help="일러스트 검수(재생성) 끄기 — 비용 절약")
    p.add_argument("--max-pause", type=float, default=Settings.max_pause, help="이보다 긴 무음은 잘라냄(초)")
    p.add_argument("--illust-every", type=float, default=Settings.seconds_per_illustration,
                   help="일러스트 최대 빈도: N초에 한 장")
    p.add_argument("--allow", default="", help="모자이크하지 않을 단어(쉼표 구분): 본인 이름, 채널명 등")
    p.add_argument("--whisper", default=Settings.whisper_model, help="Whisper 모델 (large-v3, medium, small)")
    a = p.parse_args()

    if a.rerender:
        print(render_from_plan(Path(a.rerender)))
        return
    if not a.video:
        p.error("영상 파일을 지정하거나 --rerender 를 사용하세요.")

    s = Settings(
        cut_enabled=not a.no_cut,
        illustrations_enabled=not a.no_illust,
        privacy_enabled=not a.no_privacy,
        illustration_review=not a.no_review,
        max_pause=a.max_pause,
        seconds_per_illustration=a.illust_every,
        privacy_allowlist=[x for x in a.allow.split(",") if x.strip()],
        whisper_model=a.whisper,
    )
    run(a.video, s)


if __name__ == "__main__":
    main()

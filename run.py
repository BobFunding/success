"""명령줄 실행.

  python run.py 영상.mp4
  python run.py 영상.mp4 --no-illust --allow "홍길동,내채널"
  python run.py --rerender output/영상_20261005_120000     # edit_plan.json 수정 후 최종본만 다시
  python run.py --shorts output/영상_20261005_120000       # 쇼츠(세로)만 다시 만들기
  python run.py --drive output/영상_20261005_120000        # 결과물을 구글 드라이브에 올리고 링크 출력
  python run.py --drive-login                               # 구글 드라이브 연결만 (처음 한 번 '허용')

  # 클라우드 VM(GPU 없음): 드라이브 폴더의 영상을 받아 편집하고 결과를 Output 폴더에 올리기
  #   환경 변수: OPENAI_API_KEY(받아쓰기 Whisper API), GOOGLE_SERVICE_ACCOUNT_JSON(드라이브)
  python run.py --drive-in "영상 편집/Claude Success" --drive-out Output
"""
import argparse
from pathlib import Path

from autoedit.config import Settings, load_dotenv
from autoedit.llm import LLM
from autoedit.pipeline import render_from_plan, run
from autoedit.shorts import make_shorts


def main() -> None:
    p = argparse.ArgumentParser(description="유튜브 영상 자동 편집기")
    p.add_argument("video", nargs="?", help="편집할 영상 파일")
    p.add_argument("--rerender", metavar="WORK_DIR", help="edit_plan.json 기준으로 최종본만 다시 렌더링")
    p.add_argument("--shorts", metavar="WORK_DIR", help="편집이 끝난 폴더에서 쇼츠(세로 9:16)만 다시 만들기")
    p.add_argument("--no-shorts", action="store_true", help="쇼츠(세로) 만들기 끄기")
    p.add_argument("--drive", metavar="WORK_DIR", help="결과물을 구글 드라이브에 올리고 링크 출력")
    p.add_argument("--drive-login", action="store_true", help="구글 드라이브 연결(로그인)만 하기")
    p.add_argument("--share", action="store_true", help="(--drive) 링크가 있는 누구나 보기로 공유")
    p.add_argument("--no-cut", action="store_true", help="컷 편집 끄기")
    p.add_argument("--no-illust", action="store_true", help="설명 일러스트 끄기")
    p.add_argument("--no-privacy", action="store_true", help="개인정보 처리 끄기")
    p.add_argument("--no-review", action="store_true", help="일러스트 검수(재생성) 끄기 — 비용 절약")
    p.add_argument("--max-pause", type=float, default=Settings.max_pause, help="이보다 긴 무음은 잘라냄(초)")
    p.add_argument("--illust-every", type=float, default=Settings.seconds_per_illustration,
                   help="일러스트 최대 빈도: N초에 한 장")
    p.add_argument("--allow", default="", help="모자이크하지 않을 단어(쉼표 구분): 본인 이름, 채널명 등")
    p.add_argument("--engine", choices=["gpt", "claude-svg"], default=Settings.illustration_engine,
                   help="일러스트 생성 방식: gpt(GPT 이미지 병렬 생성) / claude-svg")
    p.add_argument("--terms", default="", help="주제 용어 힌트(쉼표 구분): 받아쓰기 정확도 향상. 예: 복리,단리")
    p.add_argument("--no-correct", action="store_true", help="Claude 받아쓰기 교정 끄기")
    p.add_argument("--lang", default=Settings.language, help="받아쓰기 언어 (ko, en, ko+en=섞인 영상)")
    p.add_argument("--translate", default="", help="번역 자막 언어 (예: ko). 외국어 인터뷰에 한국어 자막")
    p.add_argument("--x264-preset", default=Settings.x264_preset, help="GPU 없을 때 인코딩 속도 (veryfast 등)")
    p.add_argument("--whisper", default=Settings.whisper_model, help="Whisper 모델 (large-v3, medium, small)")
    p.add_argument("--transcribe", choices=["auto", "local", "openai"], default=Settings.transcribe_engine,
                   help="받아쓰기 방식: auto(GPU 없고 OpenAI 키 있으면 API) / local(PC) / openai(Whisper API)")
    p.add_argument("--drive-in", metavar="FOLDER", help="이 드라이브 폴더(이름·경로·주소)의 영상을 받아 편집")
    p.add_argument("--drive-out", metavar="FOLDER", help="결과물을 올릴 드라이브 폴더(예: Output)")
    p.add_argument("--all", action="store_true", help="(--drive-in) 폴더의 영상을 전부 편집 (기본: 가장 최근 1개)")
    a = p.parse_args()

    if a.rerender:
        print(render_from_plan(Path(a.rerender)))
        return
    if a.drive_login:
        from autoedit import gdrive
        gdrive.credentials()
        print("구글 드라이브 연결 완료:", gdrive.status())
        return
    if a.drive:
        from autoedit import gdrive
        print(gdrive.links_markdown(gdrive.upload_results(Path(a.drive), share_link=a.share)))
        return
    if a.shorts:
        load_dotenv()
        print(make_shorts(Path(a.shorts), LLM(Settings.model)))
        return
    if not a.video and not a.drive_in:
        p.error("영상 파일을 지정하거나 --rerender / --drive-in 을 사용하세요.")

    s = Settings(
        cut_enabled=not a.no_cut,
        illustrations_enabled=not a.no_illust,
        privacy_enabled=not a.no_privacy,
        illustration_review=not a.no_review,
        max_pause=a.max_pause,
        seconds_per_illustration=a.illust_every,
        privacy_allowlist=[x for x in a.allow.split(",") if x.strip()],
        whisper_model=a.whisper,
        language=a.lang,
        subtitle_translate=a.translate,
        x264_preset=a.x264_preset,
        vocabulary=[x.strip() for x in a.terms.split(",") if x.strip()],
        transcript_correction=not a.no_correct,
        illustration_engine=a.engine,
        shorts_enabled=not a.no_shorts,
        transcribe_engine=a.transcribe,
    )
    if a.drive_in:
        drive_job(a.drive_in, a.drive_out, s, a.all, a.share)
        return
    work = run(a.video, s)
    if a.drive_out:
        from autoedit import gdrive
        print(gdrive.links_markdown(gdrive.upload_results(work, share_link=a.share, target=a.drive_out)))


def drive_job(src: str, dst: str | None, s: Settings, every: bool, share: bool) -> None:
    """드라이브 폴더의 영상 → 내려받기 → 자동 편집 → 결과 올리기. 영상은 input/ 에 받는다(커밋 안 함)."""
    from autoedit import gdrive
    from autoedit.config import PROJECT_DIR
    load_dotenv()
    sess = gdrive.session(interactive=False)
    folder = gdrive.find_folder(sess, src)
    videos = gdrive.list_videos(sess, folder["id"])
    if not videos:
        raise SystemExit(f"'{folder.get('name', src)}' 폴더에 영상이 없습니다.")
    for f in videos if every else videos[:1]:
        print(f"[드라이브] 편집할 영상: {f['name']}")
        local = gdrive.download_file(sess, f, PROJECT_DIR / "input")
        work = run(local, s)
        result = gdrive.upload_results(work, share_link=share, sess=sess, target=dst)
        print(gdrive.links_markdown(result))


if __name__ == "__main__":
    main()

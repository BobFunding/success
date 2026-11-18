"""웹 화면: 영상을 올리면 자동 편집 후 결과를 보여준다.  실행: python app.py"""
import queue
import threading
from pathlib import Path

import gradio as gr

from autoedit import gdrive
from autoedit.config import Settings
from autoedit.pipeline import run

EMPTY = (None, None, None, None, None, "", None)   # final, cut, gallery, report, shorts, drive_links, work


def _drive(work: Path, share: bool, log, target: str = "") -> str:
    """결과물을 드라이브에 올리고 링크 목록(마크다운)을 돌려준다. 실패하면 해야 할 일을 적어 돌려준다."""
    try:
        return gdrive.links_markdown(gdrive.upload_results(work, share_link=share, log=log,
                                                           target=target.strip() or None))
    except gdrive.DriveNotReady as e:
        return f"⚠️ {e}"
    except Exception as e:
        return f"⚠️ 드라이브에 올리지 못했습니다(편집 결과는 PC 에 그대로 있습니다): {e}"


ENGINES = {"자동 (GPU 없으면 OpenAI API)": "auto", "PC (faster-whisper, 무료)": "local",
           "OpenAI Whisper API (VM용)": "openai"}


def process(video, do_cut, do_illust, do_privacy, do_shorts, max_pause, illust_every, allow, review, terms, engine,
            stt, auto_drive, share, target):
    if not video:
        yield "영상을 먼저 올려주세요.", *EMPTY
        return
    s = Settings(
        cut_enabled=do_cut, illustrations_enabled=do_illust, privacy_enabled=do_privacy, shorts_enabled=do_shorts,
        max_pause=max_pause, seconds_per_illustration=illust_every, illustration_review=review,
        privacy_allowlist=[x for x in allow.split(",") if x.strip()],
        vocabulary=[x.strip() for x in terms.split(",") if x.strip()],
        illustration_engine="gpt" if engine.startswith("GPT") else "claude-svg",
        transcribe_engine=ENGINES.get(stt, "auto"),
    )
    logs: list[str] = []
    q: queue.Queue = queue.Queue()
    result: dict = {}

    def worker():
        try:
            result["work"] = run(video, s, log=q.put)
            if auto_drive:
                result["drive"] = _drive(result["work"], share, q.put, target)
        except Exception as e:  # 화면에 에러를 보여주기 위해
            result["error"] = e
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        msg = q.get()
        if msg is None:
            break
        logs.append(msg)
        yield "\n".join(logs[-200:]), *EMPTY

    if "error" in result:
        logs.append(f"\n❌ 오류: {result['error']}")
        yield "\n".join(logs[-200:]), *EMPTY
        return
    work: Path = result["work"]
    images = sorted(str(p) for p in (work / "illustrations").glob("*.png"))
    report = (work / "report.md").read_text(encoding="utf-8")
    logs.append(f"\n✅ 결과 폴더: {work}")
    shorts = work / "3_shorts.mp4"
    yield ("\n".join(logs[-200:]), str(work / "2_final.mp4"), str(work / "1_cut.mp4"), images, report,
           str(shorts) if shorts.exists() else None, result.get("drive", ""), str(work))


def upload_now(work, share, target):
    """'드라이브에 올리기' 버튼: 방금 편집한 결과를 올리고 링크를 보여 준다."""
    if not work:
        yield "먼저 영상을 편집해 주세요. 편집이 끝나면 이 버튼으로 올릴 수 있어요.", gdrive.status()
        return
    logs: list[str] = []
    q: queue.Queue = queue.Queue()
    out: dict = {}

    def worker():
        out["md"] = _drive(Path(work), share, q.put, target)
        q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        msg = q.get()
        if msg is None:
            break
        logs.append(msg)
        yield "올리는 중...\n\n" + "  \n".join(logs[-6:]), gdrive.status()
    yield out["md"], gdrive.status()


with gr.Blocks(title="유튜브 자동 편집기") as demo:
    gr.Markdown("## 🎬 유튜브 자동 편집기\n영상을 올리면 **무음·필러 컷 → 설명 일러스트 삽입 → 개인정보 모자이크 → 세로 쇼츠**까지 "
                "자동으로 처리하고, **구글 드라이브에 올려 링크**로 휴대폰에서도 이어 볼 수 있습니다.")
    work_state = gr.State("")
    with gr.Row():
        with gr.Column(scale=1):
            video = gr.Video(label="영상 업로드", sources=["upload"])
            with gr.Accordion("옵션", open=True):
                do_cut = gr.Checkbox(True, label="1차 컷 편집 (무음·필러 제거)")
                do_illust = gr.Checkbox(True, label="설명 일러스트 삽입")
                do_privacy = gr.Checkbox(True, label="개인정보 모자이크 / 삐- 처리")
                do_shorts = gr.Checkbox(True, label="세로 쇼츠 자동 생성 (하이라이트 30~60초, 9:16)")
                max_pause = gr.Slider(0.25, 1.5, Settings.max_pause, step=0.05,
                                      label="허용할 최대 쉼(초) — 이보다 긴 무음은 잘라냄")
                illust_every = gr.Slider(15, 120, Settings.seconds_per_illustration, step=5,
                                         label="일러스트 빈도 상한 (N초에 한 장)")
                engine = gr.Radio(["GPT 이미지 (병렬, 빠름)", "Claude SVG"], value="GPT 이미지 (병렬, 빠름)",
                                  label="일러스트 생성 방식")
                stt = gr.Radio(list(ENGINES), value=next(iter(ENGINES)), label="받아쓰기 방식")
                review = gr.Checkbox(True, label="일러스트 자동 검수 — Claude SVG 방식에만 적용 (품질↑, 비용↑)")
                allow = gr.Textbox(label="가리지 않을 단어 (쉼표 구분)", placeholder="내 이름, 채널명, 회사명")
                terms = gr.Textbox(label="영상 주제 용어 (쉼표 구분, 받아쓰기 정확도↑)", placeholder="복리, 단리, ETF")
            with gr.Accordion("구글 드라이브 (휴대폰에서 이어 보기)", open=True):
                drive_status = gr.Markdown(f"연결 상태: **{gdrive.status()}**")
                auto_drive = gr.Checkbox(False, label="편집이 끝나면 드라이브에 자동으로 올리기")
                share = gr.Checkbox(False, label="링크가 있는 누구나 보기 (끄면 나만 보기 — 같은 구글 계정 휴대폰에서 열림)")
                target = gr.Textbox(label="올릴 폴더 (비우면 '유튜브 자동 편집기' 폴더)", placeholder="Output 또는 폴더 주소")
            btn = gr.Button("자동 편집 시작", variant="primary")
        with gr.Column(scale=1):
            log_box = gr.Textbox(label="진행 상황", lines=18, max_lines=18, autoscroll=True)
            final = gr.Video(label="최종본")
            shorts = gr.Video(label="세로 쇼츠 (9:16)", height=480)
            with gr.Group():
                drive_btn = gr.Button("☁️ 구글 드라이브에 올리고 링크 만들기")
                drive_links = gr.Markdown()
    with gr.Row():
        cut = gr.Video(label="1차 컷 편집본")
        gallery = gr.Gallery(label="생성된 일러스트", columns=3, height=320)
    report = gr.Markdown()

    btn.click(process, [video, do_cut, do_illust, do_privacy, do_shorts, max_pause, illust_every, allow, review, terms,
                        engine, stt, auto_drive, share, target],
              [log_box, final, cut, gallery, report, shorts, drive_links, work_state])
    drive_btn.click(upload_now, [work_state, share, target], [drive_links, drive_status])

if __name__ == "__main__":
    demo.queue().launch(inbrowser=True, allowed_paths=[str(Path(__file__).parent / "output")])

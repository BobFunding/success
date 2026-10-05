"""웹 화면: 영상을 올리면 자동 편집 후 결과를 보여준다.  실행: python app.py"""
import queue
import threading
from pathlib import Path

import gradio as gr

from autoedit.config import Settings
from autoedit.pipeline import run


def process(video, do_cut, do_illust, do_privacy, max_pause, illust_every, allow, review, terms):
    if not video:
        yield "영상을 먼저 올려주세요.", None, None, None, None
        return
    s = Settings(
        cut_enabled=do_cut, illustrations_enabled=do_illust, privacy_enabled=do_privacy,
        max_pause=max_pause, seconds_per_illustration=illust_every, illustration_review=review,
        privacy_allowlist=[x for x in allow.split(",") if x.strip()],
        vocabulary=[x.strip() for x in terms.split(",") if x.strip()],
    )
    logs: list[str] = []
    q: queue.Queue = queue.Queue()
    result: dict = {}

    def worker():
        try:
            result["work"] = run(video, s, log=q.put)
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
        yield "\n".join(logs[-200:]), None, None, None, None

    if "error" in result:
        logs.append(f"\n❌ 오류: {result['error']}")
        yield "\n".join(logs[-200:]), None, None, None, None
        return
    work: Path = result["work"]
    images = sorted(str(p) for p in (work / "illustrations").glob("*.png"))
    report = (work / "report.md").read_text(encoding="utf-8")
    logs.append(f"\n✅ 결과 폴더: {work}")
    yield "\n".join(logs[-200:]), str(work / "2_final.mp4"), str(work / "1_cut.mp4"), images, report


with gr.Blocks(title="유튜브 자동 편집기") as demo:
    gr.Markdown("## 🎬 유튜브 자동 편집기\n영상을 올리면 **무음·필러 컷 → 설명 일러스트 삽입 → 개인정보 모자이크**까지 자동으로 처리합니다.")
    with gr.Row():
        with gr.Column(scale=1):
            video = gr.Video(label="영상 업로드", sources=["upload"])
            with gr.Accordion("옵션", open=True):
                do_cut = gr.Checkbox(True, label="1차 컷 편집 (무음·필러 제거)")
                do_illust = gr.Checkbox(True, label="설명 일러스트 삽입")
                do_privacy = gr.Checkbox(True, label="개인정보 모자이크 / 삐- 처리")
                max_pause = gr.Slider(0.25, 1.5, Settings.max_pause, step=0.05,
                                      label="허용할 최대 쉼(초) — 이보다 긴 무음은 잘라냄")
                illust_every = gr.Slider(15, 120, Settings.seconds_per_illustration, step=5,
                                         label="일러스트 빈도 상한 (N초에 한 장)")
                review = gr.Checkbox(True, label="일러스트 자동 검수 (품질↑, 비용↑)")
                allow = gr.Textbox(label="가리지 않을 단어 (쉼표 구분)", placeholder="내 이름, 채널명, 회사명")
                terms = gr.Textbox(label="영상 주제 용어 (쉼표 구분, 받아쓰기 정확도↑)", placeholder="복리, 단리, ETF")
            btn = gr.Button("자동 편집 시작", variant="primary")
        with gr.Column(scale=1):
            log_box = gr.Textbox(label="진행 상황", lines=18, max_lines=18, autoscroll=True)
            final = gr.Video(label="최종본")
    with gr.Row():
        cut = gr.Video(label="1차 컷 편집본")
        gallery = gr.Gallery(label="생성된 일러스트", columns=3, height=320)
    report = gr.Markdown()

    btn.click(process, [video, do_cut, do_illust, do_privacy, max_pause, illust_every, allow, review, terms],
              [log_box, final, cut, gallery, report])

if __name__ == "__main__":
    demo.queue().launch(inbrowser=True, allowed_paths=[str(Path(__file__).parent / "output")])

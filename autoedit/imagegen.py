"""GPT 이미지 모델로 설명 일러스트를 병렬 생성하고, 손그림 카드/설명 화면으로 합성한다."""
from __future__ import annotations

import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.sax.saxutils import escape

from .illustrate import ROUGH_FILTER, Insert, canvas_size, render_svg

CREAM = "#FFF6E5"
INK = "#2B2B2B"

STYLE_PROMPT = (
    "Flat vector illustration in a hand-drawn cartoon style. Thick, slightly wobbly dark ink outlines (#2B2B2B) "
    "with round line ends, flat fills with no gradients, a limited cheerful palette: coral #FF7A59, "
    "mustard #FFC145, mint #4CC9A6, sky blue #5AA9E6, lavender #B79CED. Cute simple characters with dot eyes "
    "and simple mouths, rounded shapes, small comic symbols (sparkles, motion lines, sweat drops) for emphasis. "
    f"Solid plain cream background ({CREAM}) filling the whole image edge to edge — no border, no frame, no shadow "
    "under the canvas, no paper texture. One clear message readable in one second: 3 to 5 elements, generous margins, "
    "nothing touching the edges. ABSOLUTELY NO TEXT: no letters, words, numbers, labels, captions or logos anywhere."
)


def _has_openai_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _gpt_size(placement: str, video_w: int, video_h: int) -> str:
    if placement == "side":
        return "1024x1024"
    return "1536x1024" if video_w >= video_h else "1024x1536"


def generate_image(client, model: str, quality: str, ins: Insert, size: str) -> bytes:
    prompt = (f"{STYLE_PROMPT}\n\nWhat to explain: {ins.concept}\nScene to draw: {ins.visual}")
    result = client.images.generate(model=model, prompt=prompt, size=size, quality=quality, n=1,
                                    output_format="png")
    return base64.b64decode(result.data[0].b64_json)


def compose(ins: Insert, art_png: bytes, art_size: str, video_w: int, video_h: int) -> tuple[str, bytes]:
    """생성된 그림을 손그림 테두리 카드(side) 또는 전체 설명 화면(full)으로 감싸고 라벨 글자를 얹는다.
    글자는 이미지 모델이 아니라 여기서 직접 그린다 (AI 이미지는 한글이 자주 깨짐)."""
    w, h = canvas_size(ins.placement, video_w, video_h)
    aw, ah = map(int, art_size.split("x"))
    data = "data:image/png;base64," + base64.b64encode(art_png).decode()
    label = escape(ins.label.strip())
    font = "font-family=\"Malgun Gothic, 'Apple SD Gothic Neo', sans-serif\" font-weight=\"800\""

    if ins.placement == "side":
        m, r = 38, 48
        cw, ch = w - 2 * m - 12, h - 2 * m - 12
        band = 150 if label else 0
        # 카드 안쪽 그림 영역 (정사각형 그림을 비율 유지로 맞춤)
        box = min(cw - 60, ch - band - 60)
        ix, iy = m + (cw - box) / 2, m + 30 + (ch - band - 60 - box) / 2
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>{ROUGH_FILTER}<clipPath id="art"><rect x="{ix}" y="{iy}" width="{box}" height="{box}" rx="28"/></clipPath></defs>
<rect x="{m + 12}" y="{m + 12}" width="{cw}" height="{ch}" rx="{r}" fill="{INK}" opacity="0.9" filter="url(#rough)"/>
<rect x="{m}" y="{m}" width="{cw}" height="{ch}" rx="{r}" fill="{CREAM}" stroke="{INK}" stroke-width="7" filter="url(#rough)"/>
<image href="{data}" x="{ix}" y="{iy}" width="{box}" height="{box}" clip-path="url(#art)" preserveAspectRatio="xMidYMid slice"/>
{f'<text x="{w / 2}" y="{m + ch - 52}" text-anchor="middle" {font} font-size="76" fill="{INK}">{label}</text>' if label else ""}
</svg>'''
    else:
        band = 170 if label else 0
        scale = min(w / aw, (h - band) / ah)
        dw, dh = aw * scale, ah * scale
        ix, iy = (w - dw) / 2, (h - band - dh) / 2
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect width="{w}" height="{h}" fill="{CREAM}"/>
<image href="{data}" x="{ix}" y="{iy}" width="{dw}" height="{dh}" preserveAspectRatio="xMidYMid meet"/>
{f'<text x="{w / 2}" y="{h - 70}" text-anchor="middle" {font} font-size="92" fill="{INK}">{label}</text>' if label else ""}
</svg>'''
    return svg, render_svg(svg, w, h)


def make_gpt_illustrations(inserts: list[Insert], video_w: int, video_h: int, out_dir: Path, settings,
                           log=print) -> list[Insert]:
    from openai import OpenAI

    out_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(max_retries=4, timeout=300)
    t0 = time.time()

    def job(idx: int, ins: Insert) -> Insert | None:
        size = _gpt_size(ins.placement, video_w, video_h)
        try:
            s = time.time()
            art = generate_image(client, settings.gpt_image_model, settings.gpt_image_quality, ins, size)
            (out_dir / f"illust_{idx:02d}_raw.png").write_bytes(art)
            svg, png = compose(ins, art, size, video_w, video_h)
            svg_path, png_path = out_dir / f"illust_{idx:02d}.svg", out_dir / f"illust_{idx:02d}.png"
            svg_path.write_text(svg, encoding="utf-8")
            png_path.write_bytes(png)
            ins.svg_path, ins.png_path = str(svg_path), str(png_path)
            log(f"[일러스트] #{idx} 완료 ({time.time() - s:.0f}초): {ins.concept}")
            return ins
        except Exception as e:
            log(f"[일러스트] #{idx} GPT 이미지 생성 실패: {e}")
            return None

    log(f"[일러스트] GPT 이미지({settings.gpt_image_model}) {len(inserts)}장을 동시에 {settings.image_workers}개씩 생성")
    results: dict[int, Insert | None] = {}
    with ThreadPoolExecutor(max_workers=settings.image_workers) as pool:
        futures = {pool.submit(job, i + 1, ins): i for i, ins in enumerate(inserts)}
        for f in as_completed(futures):
            results[futures[f]] = f.result()
    done = [results[i] for i in sorted(results) if results[i] is not None]
    log(f"[일러스트] {len(done)}/{len(inserts)}장 생성, 총 {time.time() - t0:.0f}초 (병렬)")
    return done

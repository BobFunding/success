"""이해를 돕는 설명 일러스트(플랫 벡터 + 핸드드로잉 카툰)를 기획하고 그린다."""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .llm import LLM, LLMUnavailable, image_block

# ───────────────────────── 기획 ─────────────────────────


class PlannedInsert(BaseModel):
    start: float = Field(description="일러스트가 나타날 시각(초). 해당 개념을 말하기 시작하는 문장의 시작 시각")
    end: float = Field(description="사라질 시각(초)")
    concept: str = Field(description="설명하려는 개념 한 줄 요약")
    visual: str = Field(description="그림 구성 설명: 등장 요소, 배치, 화살표/비교 구조 등 구체적으로")
    label: str = Field(description="그림에 넣을 글자. 꼭 필요할 때만 8자 이내, 필요 없으면 빈 문자열")
    placement: Literal["full", "side"] = Field(
        description="full=화면 전체를 덮는 설명 화면(요소가 여러 개인 구조/과정/비교), side=화자 옆에 뜨는 카드(단일 개념·사물)")


class InsertPlan(BaseModel):
    inserts: list[PlannedInsert]


PLAN_SYSTEM = """당신은 교육형 유튜브 영상의 모션그래픽 기획자입니다.
타임스탬프가 붙은 대본을 읽고, 시청자의 이해를 확실히 돕는 순간에만 설명 일러스트를 넣습니다.

넣기 좋은 순간:
- 추상적인 개념, 낯선 용어의 정의
- 단계/과정/흐름 (A → B → C)
- 비교/대조 (전 vs 후, 좋은 예 vs 나쁜 예)
- 숫자·비율·규모를 감각적으로 보여줄 때
- 원인과 결과, 구조와 관계

넣지 말아야 할 순간: 인사, 잡담, 농담, 감정 표현, 구독 요청, 이미 쉬운 말.

규칙:
- 일러스트는 글자를 최소화한 그림으로 이해시키는 것이 목적입니다. label 은 꼭 필요할 때만 짧게.
- 시작 시각은 그 개념을 말하기 시작하는 문장의 시작 시각에 맞춥니다.
- 일러스트끼리 겹치지 않게, 최소 8초 이상 간격을 둡니다.
- visual 은 그림 작가가 바로 그릴 수 있게 구체적으로 씁니다 (등장 사물, 캐릭터 표정, 배치, 화살표)."""


@dataclass
class Insert:
    start: float
    end: float
    concept: str
    visual: str
    label: str
    placement: str
    svg_path: str = ""
    png_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def plan_inserts(sentences: list[dict], total: float, llm: LLM, per_sec: float,
                 min_dur: float, max_dur: float, log=print) -> list[Insert]:
    max_count = max(1, math.floor(total / per_sec))
    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in sentences)
    prompt = (f"영상 길이: {total:.1f}초. 일러스트는 최대 {max_count}개, 각각 {min_dur:.0f}~{max_dur:.0f}초 길이.\n"
              f"정말 도움이 되는 곳에만 넣고, 적절한 곳이 적으면 더 적게 넣어도 됩니다.\n\n대본:\n{transcript}")
    plan = llm.parse(PLAN_SYSTEM, prompt, InsertPlan, effort="high")

    inserts: list[Insert] = []
    for p in sorted(plan.inserts, key=lambda x: x.start):
        start = max(0.0, min(p.start, total - min_dur))
        end = min(total, max(start + min_dur, min(p.end, start + max_dur)))
        if inserts and start < inserts[-1].end + 2.0:
            continue
        inserts.append(Insert(round(start, 2), round(end, 2), p.concept, p.visual, p.label.strip()[:12], p.placement))
    log(f"[일러스트] {len(inserts)}개 삽입 지점 선정")
    return inserts[:max_count]


# ───────────────────────── 그리기 ─────────────────────────

ROUGH_FILTER = """<filter id="rough" x="-10%" y="-10%" width="120%" height="120%">
  <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="7" result="noise"/>
  <feDisplacementMap in="SourceGraphic" in2="noise" scale="5" xChannelSelector="R" yChannelSelector="G"/>
</filter>"""

DRAW_SYSTEM = f"""당신은 유튜브 설명 영상용 일러스트레이터입니다. 요청받은 장면을 SVG 코드 하나로 그립니다.

[스타일: 플랫 벡터 + 핸드드로잉 카툰]
- 면은 그라데이션 없는 플랫 컬러. 팔레트는 5~6색 이내로 통일:
  크림 배경 #FFF6E5, 잉크 #2B2B2B, 코랄 #FF7A59, 머스터드 #FFC145, 민트 #4CC9A6, 스카이 #5AA9E6, 연보라 #B79CED
- 외곽선은 잉크색 두꺼운 선(stroke-width 5~8), stroke-linecap/linejoin="round".
- 손으로 그린 느낌: 아래 필터를 <defs>에 그대로 넣고, 외곽선/도형 그룹에 filter="url(#rough)" 적용.
  선은 완벽한 직선 대신 살짝 휘어진 path 를 쓰고, 화살표도 손으로 그은 곡선 + 삐뚤한 화살촉.
{ROUGH_FILTER}
- 귀엽고 단순한 카툰: 사람/사물 캐릭터는 점 눈, 단순한 입, 둥글둥글한 형태. 강조용 반짝이·땀방울·움직임 선 같은 만화 기호 활용.
- 그림자는 블러 대신 살짝 어긋난 단색 도형(잉크 10~15% 투명도)으로.

[글자 최소화]
- 요청에 label 이 있으면 그 글자만 크고 굵게(font-weight 800, 72px 이상) 한 번 넣습니다. label 이 없으면 글자를 넣지 마세요.
- 꼭 필요한 숫자/기호(%, →, ✕, ✓)는 허용합니다. 그 외 설명문·제목·캡션 금지.
- font-family="Malgun Gothic, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"

[구도]
- 핵심 메시지 하나가 1초 안에 읽히도록 단순하게. 요소 3~5개 이내, 여백 충분히.
- 모든 요소는 캔버스 안쪽 6% 여백 안에 들어와야 하며 잘리면 안 됩니다.

[기술 제약]
- <svg xmlns="http://www.w3.org/2000/svg" width=W height=H viewBox="0 0 W H"> 로 시작.
- 외부 리소스, <image>, <foreignObject>, <script>, CSS @import, 웹폰트 금지.
- 응답은 SVG 코드만. 설명이나 마크다운 코드블록 없이 <svg 로 시작해서 </svg> 로 끝내세요."""

REVIEW_SYSTEM = """당신은 일러스트 검수자입니다. 렌더링된 이미지와 SVG 원본을 보고 아래 문제가 있는지 확인합니다.
- 요소가 캔버스 밖으로 잘림, 요소끼리 어색하게 겹침, 무엇을 그렸는지 알아볼 수 없음
- 요청하지 않은 글자/문장이 들어감, 글자가 깨지거나 넘침
- 핸드드로잉 카툰 + 플랫 벡터 스타일이 아님
문제가 없으면 정확히 OK 한 단어만 답하세요.
문제가 있으면 고친 SVG 전체만 답하세요 (<svg 로 시작해서 </svg> 로 끝, 다른 설명 없이)."""


def canvas_size(placement: str, video_w: int, video_h: int) -> tuple[int, int]:
    if placement == "side":
        return 960, 960
    return (1920, 1080) if video_w >= video_h else (1080, 1920)


def _extract_svg(text: str) -> str | None:
    m = re.search(r"<svg[\s\S]*</svg>", text)
    return m.group(0) if m else None


def _sanitize(svg: str) -> str:
    svg = re.sub(r"<script[\s\S]*?</script>", "", svg, flags=re.I)
    svg = re.sub(r"<foreignObject[\s\S]*?</foreignObject>", "", svg, flags=re.I)
    svg = re.sub(r"<image\b[^>]*/?>", "", svg, flags=re.I)
    if 'url(#rough)' in svg and 'id="rough"' not in svg:
        if "<defs>" in svg:
            svg = svg.replace("<defs>", "<defs>" + ROUGH_FILTER, 1)
        else:
            svg = re.sub(r"(<svg\b[^>]*>)", r"\1<defs>" + ROUGH_FILTER + "</defs>", svg, count=1)
    return svg


def render_svg(svg: str, width: int, height: int) -> bytes:
    import resvg_py
    # 시스템 폰트(맑은 고딕 포함)는 기본으로 로드된다
    data = resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height,
                                 font_family="Malgun Gothic", sans_serif_family="Malgun Gothic")
    return bytes(data)


def _context(sentences: list[dict], ins: Insert) -> str:
    near = [s["text"] for s in sentences if s["end"] >= ins.start - 6 and s["start"] <= ins.end + 4]
    return " ".join(near)


def draw_insert(ins: Insert, idx: int, sentences: list[dict], llm: LLM, video_w: int, video_h: int,
                out_dir: Path, review: bool, log=print) -> Insert | None:
    w, h = canvas_size(ins.placement, video_w, video_h)
    if ins.placement == "side":
        layout = ("화자 옆에 뜨는 카드입니다. 캔버스 전체가 아니라, 가장자리 4% 안쪽에 둥근 모서리(rx 48) 크림색 카드를 그리고 "
                  "카드 아래·오른쪽으로 12px 어긋난 잉크색(투명도 0.9) 카드 그림자를 둡니다. 카드 바깥은 투명하게 비워두세요. "
                  "카드 테두리도 손그림 느낌(rough 필터)으로.")
    else:
        layout = "화면 전체를 덮는 설명 화면입니다. 크림색 배경을 캔버스 전체에 깔고, 종이 질감 느낌의 옅은 낙서 점/선을 배경에 살짝 흩뿌려도 좋습니다."
    prompt = (f"캔버스: width={w} height={h}\n배치: {layout}\n\n"
              f"설명할 개념: {ins.concept}\n그림 구성: {ins.visual}\n"
              f"label: {ins.label if ins.label else '(없음 — 글자 넣지 말 것)'}\n\n"
              f"이 장면에서 화자가 하는 말(참고): {_context(sentences, ins)}")
    try:
        svg = None
        for attempt in range(2):
            svg = _extract_svg(llm.text(DRAW_SYSTEM, prompt, effort="medium"))
            if svg:
                break
        if not svg:
            log(f"[일러스트] #{idx} SVG 생성 실패, 건너뜀")
            return None
        svg = _sanitize(svg)
        png = render_svg(svg, w, h)

        if review:
            reply = llm.text(REVIEW_SYSTEM, [
                image_block(png),
                {"type": "text", "text": f"요청 내용:\n{prompt}\n\nSVG 원본:\n{svg}"},
            ], effort="medium")
            fixed = _extract_svg(reply)
            if fixed:
                try:
                    fixed = _sanitize(fixed)
                    png = render_svg(fixed, w, h)
                    svg = fixed
                    log(f"[일러스트] #{idx} 검수 후 수정됨")
                except Exception as e:
                    log(f"[일러스트] #{idx} 수정본 렌더링 실패, 원본 사용: {e}")

        svg_path = out_dir / f"illust_{idx:02d}.svg"
        png_path = out_dir / f"illust_{idx:02d}.png"
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(png)
        ins.svg_path, ins.png_path = str(svg_path), str(png_path)
        log(f"[일러스트] #{idx} 완료: {ins.concept}")
        return ins
    except LLMUnavailable as e:
        log(f"[일러스트] #{idx} Claude 호출 실패: {e}")
    except Exception as e:
        log(f"[일러스트] #{idx} 실패: {e}")
    return None


def make_illustrations(sentences: list[dict], total: float, llm: LLM, video_w: int, video_h: int,
                       out_dir: Path, settings, log=print) -> list[Insert]:
    if not llm.available:
        log("[일러스트] Claude API 키가 없어 일러스트 단계를 건너뜁니다.")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        inserts = plan_inserts(sentences, total, llm, settings.seconds_per_illustration,
                               settings.min_illustration_sec, settings.max_illustration_sec, log)
    except LLMUnavailable as e:
        log(f"[일러스트] 기획 실패: {e}")
        return []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda pair: draw_insert(pair[1], pair[0] + 1, sentences, llm, video_w, video_h, out_dir,
                                     settings.illustration_review, log),
            enumerate(inserts)))
    return [r for r in results if r is not None]

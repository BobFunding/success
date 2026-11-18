"""쇼츠(세로 9:16) 자동 생성: 컷 편집본에서 하이라이트 30~60초를 골라 세로 영상으로 만든다.

- 구간 고르기: Claude가 문장 목록을 보고 혼자 봐도 이해되고 첫 문장이 흥미를 끄는 구간을 고른다.
  키가 없거나 응답이 이상하면 규칙(말이 가장 촘촘한 구간)으로 고른다.
- 화면: 얼굴이 자주 보이면 얼굴을 따라가며 세로로 자르고(crop), 아니면(화면 녹화 등)
  흐린 배경 위에 원본을 통째로 얹는다(fit).
- 개인정보: 최종본과 같은 모자이크·삐- 를 구간 시간에 맞춰 그대로 적용하고, 자막·제목도 가린 대본으로 만든다.
- 위쪽에 짧은 제목, 아래쪽에 큰 자막.
결과: 작업 폴더의 3_shorts.mp4, shorts.json (구간·제목·이유·화면 방식)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel

from .config import Settings
from .ffmpeg_utils import VideoInfo, filter_script_args, probe, run_ffmpeg, video_encoder_args
from .llm import LLMUnavailable
from .render import render_final
from .transcribe import Word, group_sentences

OUT_W, OUT_H = 1080, 1920


class ShortsPick(BaseModel):
    start_index: int   # 쇼츠가 시작하는 문장 번호
    end_index: int     # 쇼츠가 끝나는 문장 번호 (포함)
    title: str         # 화면 위쪽에 띄울 짧은 제목
    reason: str        # 이 구간을 고른 이유 (리포트용)


PICK_SYSTEM = """당신은 유튜브 쇼츠 편집자입니다. 긴 영상의 대본(문장 목록)을 보고 쇼츠로 잘라 낼 구간 하나를 고릅니다.
규칙:
- 연속된 문장 [start_index..end_index] 하나만 고릅니다. 길이는 {min_len:.0f}~{max_len:.0f}초 사이여야 합니다.
- 앞뒤 맥락 없이 혼자 봐도 이해되는 구간을 고릅니다(앞 내용을 가리키는 '그래서', '아까 말한' 으로 시작하지 않게).
- 첫 문장이 질문·숫자·의외의 사실처럼 흥미를 끄는 곳이면 좋습니다. 끝은 문장이 끝나는 곳으로 합니다.
- title 은 화면 위쪽에 띄울 제목입니다. 16자 이내, 영상 내용 그대로(과장·낚시 금지), 개인정보·'(삐-)' 금지.
- reason 은 한 문장으로 씁니다."""


# ── 1. 구간 고르기 ──

def _duration(sents: list[dict], i: int, j: int) -> float:
    return sents[j]["end"] - sents[i]["start"]


GREETING = ("안녕하세요", "안녕하십니까", "반갑습니다", "여러분 안녕")
CLOSING = ("감사합니다", "고맙습니다", "구독", "다음 영상", "다음 시간")
HOOK = ("?", "첫째", "가지", "비밀", "이유", "방법", "꼭", "절대")


def _start_score(text: str) -> float:
    """구간 첫 문장 점수: 인사로 시작하면 깎고, 질문·숫자·'~가지/방법' 같은 말로 시작하면 더한다."""
    t = text.strip()
    score = -3.0 if t.startswith(GREETING) else 0.0
    if any(h in t for h in HOOK) or any(c.isdigit() for c in t):
        score += 1.0
    return score


def fallback_pick(sents: list[dict], min_len: float, max_len: float) -> tuple[int, int]:
    """규칙으로 고르기: 길이 조건을 맞추는 구간 중 말이 가장 촘촘한(초당 글자 수가 많은) 곳.
    인사말로 시작하거나 맺음말로 끝나는 구간은 깎고, 질문·숫자로 시작하면 더한다.
    조건을 맞추는 구간이 없으면 처음부터 max_len 안쪽까지."""
    best, best_score = None, -1e9
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            d = _duration(sents, i, j)
            if d > max_len:
                break
            if d < min_len:
                continue
            chars = sum(len(s["text"].replace(" ", "")) for s in sents[i:j + 1])
            score = chars / max(d, 1e-6) + _start_score(sents[i]["text"])
            if any(c in sents[j]["text"] for c in CLOSING):
                score -= 1.0
            if score > best_score:
                best, best_score = (i, j), score
    if best:
        return best
    j = 0
    while j + 1 < len(sents) and _duration(sents, 0, j + 1) <= max_len:
        j += 1
    return 0, j


def _fallback_title(text: str, limit: int = 16) -> str:
    """규칙 제목: 인사말·'오늘은' 같은 앞말을 떼고, 단어 단위로 limit 글자 안쪽에서 끊는다."""
    t = text.replace("(삐-)", "").strip()
    for g in GREETING:
        if t.startswith(g):
            t = t[len(g):].lstrip(" ,.!")
    for lead in ("오늘은 ", "오늘 ", "자, ", "그럼 ", "이번에는 "):
        if t.startswith(lead):
            t = t[len(lead):]
    t = t.rstrip(".,!? ")
    if len(t) <= limit:
        return t
    out = ""
    for w in t.split():
        if len(out) + len(w) + (1 if out else 0) > limit:
            break
        out = f"{out} {w}".strip()
    return out or t[:limit]


def pick_highlight(sents: list[dict], llm, min_len: float = 30.0, max_len: float = 60.0, log=print) -> dict:
    """하이라이트 구간 하나를 고른다. sents 는 가린 대본으로 만든 문장 목록(컷 편집본 시간)."""
    if not sents:
        raise ValueError("문장이 없습니다")
    total = sents[-1]["end"] - sents[0]["start"]
    if total <= max_len:   # 영상 전체가 쇼츠 길이 안쪽이면 통째로 쓴다
        return {"i": 0, "j": len(sents) - 1, "title": _fallback_title(sents[0]["text"]),
                "reason": "영상 전체가 쇼츠 길이 안쪽", "by": "rule"}
    if llm is not None and getattr(llm, "available", False):
        listing = "\n".join(f"[{k}] {s['start']:.1f}~{s['end']:.1f}초  {s['text']}" for k, s in enumerate(sents))
        try:
            p = llm.parse(PICK_SYSTEM.format(min_len=min_len, max_len=max_len),
                          f"문장 목록 (컷 편집본 기준 시간):\n{listing}", ShortsPick, effort="low", max_tokens=2000)
            i, j = p.start_index, p.end_index
            if 0 <= i <= j < len(sents) and min_len * 0.8 <= _duration(sents, i, j) <= max_len * 1.1:
                title = p.title.replace("(삐-)", "").strip()
                if title and len(title) <= 24:
                    return {"i": i, "j": j, "title": title, "reason": p.reason.strip(), "by": "claude"}
            log(f"[쇼츠] Claude가 고른 구간이 조건에 맞지 않아 규칙으로 고릅니다 ({i}~{j}).")
        except (LLMUnavailable, Exception) as e:  # 응답 오류도 규칙으로 대신한다
            log(f"[쇼츠] Claude 구간 선택 실패 → 규칙으로 고릅니다: {e}")
    i, j = fallback_pick(sents, min_len, max_len)
    return {"i": i, "j": j, "title": _fallback_title(sents[i]["text"]),
            "reason": "말이 가장 촘촘한 구간(규칙)", "by": "rule"}


def shift_items(items: list[dict], start: float, end: float) -> list[dict]:
    """모자이크·삐- 목록을 [start, end] 구간 기준 시간으로 옮긴다. 구간과 겹치지 않는 것은 버린다."""
    out = []
    for it in items:
        if it["end"] <= start or it["start"] >= end:
            continue
        c = dict(it)
        c["start"] = max(0.0, it["start"] - start)
        c["end"] = min(end, it["end"]) - start
        out.append(c)
    return out


def shift_words(words: list[Word], start: float, end: float) -> list[Word]:
    return [Word(round(w.start - start, 3), round(w.end - start, 3), w.text, w.prob)
            for w in words if w.end > start and w.start < end]


# ── 2. 얼굴 따라가기 ──

def smooth_path(samples: list[tuple[float, float | None]], min_hit: float = 0.4,
                dead_zone: float = 0.04, window: int = 5) -> list[tuple[float, float]] | None:
    """(시각, 얼굴 가운데 x 비율 또는 None) 목록 → 흔들리지 않는 카메라 경로.
    얼굴이 잡힌 비율이 min_hit 보다 낮으면 None (얼굴 따라가기를 쓰지 않음)."""
    if not samples:
        return None
    hits = [x for _, x in samples if x is not None]
    if len(hits) < max(2, min_hit * len(samples)):
        return None
    # 못 찾은 곳은 가장 가까운 찾은 값으로 채운다
    xs: list[float] = []
    for k, (_, x) in enumerate(samples):
        if x is None:
            near = min((abs(k - m), samples[m][1]) for m in range(len(samples)) if samples[m][1] is not None)
            x = near[1]
        xs.append(x)
    # 이동 중앙값으로 튀는 값 제거 → 작은 움직임은 무시(데드존)
    half = window // 2
    med = [sorted(xs[max(0, k - half):k + half + 1])[len(xs[max(0, k - half):k + half + 1]) // 2]
           for k in range(len(xs))]
    path: list[tuple[float, float]] = []
    cur = med[0]
    for (t, _), x in zip(samples, med):
        if abs(x - cur) > dead_zone:
            cur = x
        path.append((t, cur))
    # 값이 바뀌는 곳만 남겨 식을 짧게 (처음·끝은 항상)
    keep = [path[0]] + [p for k, p in enumerate(path[1:-1], 1) if p[1] != path[k - 1][1]] + [path[-1]]
    return keep


def detect_faces(video: Path, start: float, end: float, step: float = 0.5) -> list[tuple[float, float | None]]:
    """[start, end] 구간을 step 초마다 보고, 가장 큰 얼굴의 가운데 x(화면 너비 비율)를 돌려준다."""
    import cv2
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    cap = cv2.VideoCapture(str(video))
    out: list[tuple[float, float | None]] = []
    t = start
    try:
        while t < end:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            scale = 640 / w if w > 640 else 1.0
            small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale != 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6,
                                             minSize=(max(24, small.shape[0] // 12),) * 2)
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                out.append((t - start, (x + fw / 2) / small.shape[1]))
            else:
                out.append((t - start, None))
            t += step
    finally:
        cap.release()
    return out


def crop_x_expr(path: list[tuple[float, float]], src_w: int, crop_w: int) -> str:
    """카메라 경로 → ffmpeg crop 의 x 식. 키프레임 사이를 0.6초에 걸쳐 부드럽게(smoothstep) 옮긴다."""
    def x_of(c: float) -> float:
        return min(max(c * src_w - crop_w / 2, 0), src_w - crop_w)
    x0 = x_of(path[0][1])
    terms = [f"{x0:.1f}"]
    prev = x0
    for t, c in path[1:]:
        x = x_of(c)
        d = x - prev
        if abs(d) >= 1:
            u = f"clip((t-{max(0.0, t - 0.6):.2f})/0.6,0,1)"
            terms.append(f"{d:+.1f}*({u}*{u}*(3-2*{u}))")
        prev = x
    return "+".join(terms).replace("+-", "-")


# ── 3. 글자(ASS) ──

def _ass_ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_shorts_ass(path: Path, title: str, cues: list[tuple[float, float, str]], duration: float,
                     font: str, mode: str) -> None:
    """위쪽 제목(노란 상자) + 아래쪽 큰 자막(흰 글자, 두꺼운 테두리). 1080x1920 기준."""
    sub_margin = 520 if mode == "fit" else 430     # 아래에서부터 거리
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OUT_W}", f"PlayResY: {OUT_H}",
             "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
             "Alignment, MarginL, MarginR, MarginV, Encoding",
             # 제목: 검은 글자 + 노란 상자(BorderStyle 3)
             f"Style: Title,{font},78,&H00141414,&H00141414,&H0022D7FF,&H0022D7FF,-1,0,0,0,100,100,0,0,3,"
             f"18,0,8,70,70,230,1",
             f"Style: Sub,{font},86,&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,1,"
             f"7,3,2,80,80,{sub_margin},1", "",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    clean = lambda s: s.replace("{", "(").replace("}", ")").replace("\n", " ")   # noqa: E731
    if title:
        lines.append(f"Dialogue: 1,{_ass_ts(0)},{_ass_ts(duration)},Title,,0,0,0,,{clean(title)}")
    for s, e, text in cues:
        lines.append(f"Dialogue: 0,{_ass_ts(s)},{_ass_ts(min(e, duration))},Sub,,0,0,0,,{clean(text)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 4. 만들기 ──

def _seg_info(info: VideoInfo, dur: float) -> VideoInfo:
    return VideoInfo(info.width, info.height, info.fps, dur, info.has_audio)


def make_shorts(work: Path, llm=None, log=print) -> Path | None:
    """작업 폴더(편집이 끝난 곳)에서 쇼츠를 만든다. 대본이 없으면 만들지 않는다."""
    from .pipeline import masked_words, subtitle_cues   # 순환 import 방지

    plan = json.loads((work / "edit_plan.json").read_text(encoding="utf-8"))
    settings = Settings(**plan["settings"])
    transcript = work / "transcript_cut.json"
    words = [Word(**w) for w in json.loads(transcript.read_text(encoding="utf-8"))] if transcript.exists() else []
    if not words:
        log("[쇼츠] 말소리 대본이 없어 쇼츠를 만들지 않습니다.")
        return None
    cut_video = work / "1_cut.mp4"
    info = probe(cut_video)
    beeps = plan.get("beeps", [])
    shown = masked_words(words, beeps)                       # 개인정보를 가린 대본으로만 고르고 자막을 만든다
    sents = group_sentences(shown)
    pick = pick_highlight(sents, llm, settings.shorts_min, settings.shorts_max, log)
    start = max(0.0, sents[pick["i"]]["start"] - 0.15)
    end = min(info.duration, sents[pick["j"]]["end"] + 0.35)
    dur = end - start
    log(f"[쇼츠] {start:.1f}~{end:.1f}초 ({dur:.0f}초) 선택 — {pick['reason']}")

    tmp = work / "shorts_tmp"
    tmp.mkdir(exist_ok=True)
    # (1) 구간 잘라 내기 (정확한 위치에서 자르려고 다시 인코딩)
    seg = tmp / "seg.mp4"
    run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(cut_video),
                *video_encoder_args(16, "veryfast"), "-c:a", "aac", "-b:a", "192k", str(seg)], log)
    # (2) 최종본과 같은 모자이크·삐- 를 구간 시간에 맞춰 적용 (일러스트·가로 자막은 넣지 않음)
    seg_info = probe(seg)
    safe = tmp / "seg_private.mp4"
    render_final(seg, safe, seg_info, shift_items(plan.get("mosaics", []), start, end),
                 shift_items(beeps, start, end), [], settings.mosaic_block, 16, tmp, log, x264_preset="veryfast")

    # (3) 세로 화면 방식 정하기
    W, H = seg_info.width, seg_info.height
    path = None
    if W > H:
        try:
            path = smooth_path(detect_faces(safe, 0.0, seg_info.duration))
        except Exception as e:  # opencv 가 없거나 읽기 실패 → 흐린 배경 방식
            log(f"[쇼츠] 얼굴 찾기를 건너뜁니다: {e}")
    mode = "crop" if path else "fit"
    log(f"[쇼츠] 화면 방식: {'얼굴 따라 세로로 자르기' if mode == 'crop' else '흐린 배경 위에 원본 얹기'}")

    # (4) 세로 합성 + 제목·자막
    cues = subtitle_cues(shift_words(words, start, end), shift_items(beeps, start, end), max_chars=14)
    ass = tmp / "shorts.ass"
    write_shorts_ass(ass, pick["title"], cues, seg_info.duration, settings.subtitle_font, mode)
    name = ass.resolve().as_posix().replace(":", "\\:")
    if mode == "crop":
        cw = min(W, int(H * 9 / 16) // 2 * 2)
        graph = (f"[0:v]crop={cw}:{H}:x='{crop_x_expr(path, W, cw)}':y=0,"
                 f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1,ass=filename='{name}'[vout]")
    else:
        fg_h = int(OUT_W * H / W) // 2 * 2
        y = max(0, (OUT_H - fg_h) // 2 - 60)
        graph = (f"[0:v]split=2[bgs][fgs];"
                 f"[bgs]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
                 f"boxblur=40:3,eq=brightness=-0.12[bg];"
                 f"[fgs]scale={OUT_W}:{fg_h}:flags=lanczos[fg];"
                 f"[bg][fg]overlay=0:{y},setsar=1,ass=filename='{name}'[vout]")
    script = tmp / "shorts_filter.txt"
    script.write_text(graph, encoding="utf-8")
    dst = work / "3_shorts.mp4"
    fade = min(0.15, seg_info.duration / 10)
    audio = (["-map", "0:a", "-af", f"afade=t=in:d={fade:.2f},afade=t=out:st={seg_info.duration - fade:.2f}:d={fade:.2f}",
              "-c:a", "aac", "-b:a", "192k"] if seg_info.has_audio else [])
    run_ffmpeg(["-i", str(safe), *filter_script_args(script), "-map", "[vout]", *audio,
                *video_encoder_args(settings.quality_cq, settings.x264_preset), "-r", f"{min(seg_info.fps, 60):.3f}",
                "-movflags", "+faststart", str(dst)], log)

    meta = {"start": round(start, 2), "end": round(end, 2), "duration": round(dur, 2), "title": pick["title"],
            "reason": pick["reason"], "picked_by": pick["by"], "mode": mode,
            "text": " ".join(s["text"] for s in sents[pick["i"]:pick["j"] + 1])}
    (work / "shorts.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in tmp.glob("*.mp4"):
        p.unlink()
    log(f"[쇼츠] 완료: {dst.name} ({math.ceil(dur)}초, 제목 \"{pick['title']}\")")
    return dst

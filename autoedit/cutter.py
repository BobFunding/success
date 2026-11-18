"""1차 컷 편집: 무음 구간과 필러워드("어", "음")를 잘라낸다."""
from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from .ffmpeg_utils import VideoInfo, filter_script_args, run_ffmpeg, video_encoder_args
from .llm import LLM, LLMUnavailable
from .transcribe import Word

_PUNCT = re.compile(r"[\s.,!?…~\-\"'“”‘’()]+")

# 어떤 문맥에서도 의미가 없는 말버릇 → 무조건 컷
STRONG_FILLER = re.compile(r"^(어|음|으|엄|흠|어음|으음|음음|어어|에|에에|아아|어후|하아"
                           r"|u+h+|u+m+|uh+m+|e+r+m*|h+m+)+$", re.IGNORECASE)  # 영어 필러: uh, um, uhm, er, hmm
# 의미가 있을 수도 있는 말 → Claude 가 문맥 보고 판단 (API 키 없으면 남겨둠)
WEAK_FILLER = re.compile(r"^(아|그|저|뭐|막|이제|약간|좀|그니까|그러니까|그래서|저기|이렇게|뭐랄까|있잖아|있잖아요|네|예)$")


def normalize(text: str) -> str:
    return _PUNCT.sub("", text)


# ───────────────────────── 필러 판정 ─────────────────────────

class FillerCut(BaseModel):
    index: int = Field(description="잘라낼 단어의 번호")
    reason: str = Field(description="짧은 이유: 필러 / 말더듬 / 반복")


class FillerDecision(BaseModel):
    cuts: list[FillerCut]


FILLER_SYSTEM = """당신은 한국어 유튜브 영상의 1차 컷 편집자입니다.
번호가 붙은 단어 목록(받아쓰기 결과)을 보고, 잘라내도 의미 전달에 전혀 지장이 없는 단어만 고릅니다.

잘라도 되는 것:
- 의미 없는 말버릇: "어", "음", "아", 의미 없이 끼어든 "그", "저", "뭐", "막", "이제", "약간"
- 말더듬/반복: "그래서 그래서" → 앞의 것, "이거 이거" → 앞의 것
- 바로 고쳐 말한 시작 부분: "내일, 아니 모레" 에서는 자르지 마세요(의미가 있음). 단, 단어가 중간에 끊긴 실패한 시작("하, 하는")은 앞의 것만 자릅니다.

절대 자르지 말 것:
- 지시어로 쓰인 "그 사람", "저 버튼", "이제 시작합니다(지금이라는 뜻)"처럼 뜻이 있는 단어
- 대답 "네", 감탄으로 감정을 전달하는 "아!" 등 시청자가 맥락상 들어야 하는 말
- 확신이 없으면 자르지 않습니다. 과하게 자르면 영상이 부자연스러워집니다.

[후보] 표시는 규칙으로 찾은 의심 단어입니다. 후보가 아닌 단어도 말더듬/반복이면 고를 수 있습니다."""


def decide_fillers(words: list[Word], llm: LLM | None, log=print) -> dict[int, str]:
    """잘라낼 단어 번호 → 이유."""
    cuts: dict[int, str] = {}
    weak: set[int] = set()
    for i, w in enumerate(words):
        n = normalize(w.text)
        if not n:
            continue
        if STRONG_FILLER.match(n) and (w.end - w.start) < 2.0:
            cuts[i] = "필러"
        elif WEAK_FILLER.match(n):
            weak.add(i)

    if llm is None or not llm.available:
        log(f"[컷] 필러 {len(cuts)}개 (규칙 기반, 애매한 후보 {len(weak)}개는 유지)")
        return cuts

    chunk = 700
    for start in range(0, len(words), chunk):
        end = min(len(words), start + chunk)
        ctx_start, ctx_end = max(0, start - 20), min(len(words), end + 20)
        lines = []
        for i in range(ctx_start, ctx_end):
            tag = " [후보]" if (i in weak or i in cuts) else ""
            lines.append(f"{i}: {words[i].text}{tag}")
        prompt = (f"단어 {start}~{end - 1} 번 중에서 잘라낼 단어를 골라주세요 "
                  f"(앞뒤 번호는 문맥 참고용).\n\n" + "\n".join(lines))
        try:
            decision = llm.parse(FILLER_SYSTEM, prompt, FillerDecision, effort="medium")
        except LLMUnavailable as e:
            log(f"[컷] Claude 필러 판단 실패, 규칙 기반으로 진행: {e}")
            return cuts
        for c in decision.cuts:
            if start <= c.index < end and (words[c.index].end - words[c.index].start) < 2.5:
                cuts[c.index] = c.reason
    log(f"[컷] 잘라낼 필러/말더듬 {len(cuts)}개")
    return cuts


# ───────────────────────── 무음 감지 ─────────────────────────

def detect_silences(wav_path: Path, min_len: float) -> list[tuple[float, float]]:
    """음량이 배경소음 수준인 구간을 찾는다. 임계값은 영상마다 자동 계산."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(sr * 0.02)
    n = len(audio) // hop
    if n == 0:
        return []
    frames = audio[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    noise, speech = np.percentile(db, 10), np.percentile(db, 90)
    threshold = noise + max(6.0, 0.3 * (speech - noise))
    quiet = db < threshold

    silences = []
    i = 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            s, e = i * 0.02, j * 0.02
            if e - s >= min_len:
                silences.append((s, e))
            i = j
        else:
            i += 1
    return silences


# ───────────────────────── 남길 구간 계산 ─────────────────────────

def compute_keep_segments(words: list[Word], cut_idx: dict[int, str], silences: list[tuple[float, float]],
                          duration: float, pad: float, max_pause: float, min_segment: float) -> list[tuple[float, float]]:
    if not words:
        return [(0.0, duration)]

    # 1) 단어 기준: 남길 단어들을 묶되, 사이에 잘린 단어가 있거나 간격이 길면 끊는다
    segments: list[list[float]] = []
    prev_kept: Word | None = None
    cut_since_prev: list[Word] = []
    for i, w in enumerate(words):
        if i in cut_idx:
            cut_since_prev.append(w)
            continue
        if prev_kept is None:
            start = w.start - pad
            if cut_since_prev:
                start = max(start, cut_since_prev[-1].end)
            segments.append([max(0.0, start), w.end + pad])
        else:
            gap = w.start - prev_kept.end
            if not cut_since_prev and gap <= max_pause:
                segments[-1][1] = w.end + pad
            else:
                seg_end = prev_kept.end + pad
                seg_start = w.start - pad
                if cut_since_prev:  # 잘린 필러 소리가 pad 로 다시 들어오지 않게
                    seg_end = min(seg_end, max(prev_kept.end, cut_since_prev[0].start))
                    seg_start = max(seg_start, min(w.start, cut_since_prev[-1].end))
                segments[-1][1] = seg_end
                segments.append([seg_start, w.end + pad])
        prev_kept = w
        cut_since_prev = []
    for seg in segments:
        seg[1] = min(seg[1], duration)

    # 2) 음량 기준: Whisper 타임스탬프가 무음까지 늘어나는 경우가 있어 긴 무음은 한 번 더 깎는다
    for s, e in silences:
        if e - s <= max_pause:
            continue
        hole = (s + pad, e - pad)
        new = []
        for a, b in segments:
            if hole[1] <= a or hole[0] >= b:
                new.append([a, b])
                continue
            if hole[0] > a:
                new.append([a, hole[0]])
            if hole[1] < b:
                new.append([hole[1], b])
        segments = new

    # 3) 겹침 병합 + 너무 짧은 조각 제거
    segments.sort()
    merged: list[list[float]] = []
    for a, b in segments:
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= min_segment]


def snap_to_frames(segments: list[tuple[float, float]], fps: float) -> list[tuple[float, float]]:
    """구간 경계를 프레임 경계에 맞춘다. 영상은 프레임 단위, 오디오는 샘플 단위로 잘리므로
    맞추지 않으면 구간마다 최대 1프레임씩 어긋남이 쌓여 입 모양과 소리가 틀어진다."""
    out = []
    for a, b in segments:
        fa, fb = round(a * fps), round(b * fps)
        if fb > fa:
            out.append((fa / fps, fb / fps))
    return out


# ───────────────────────── 시간 변환 ─────────────────────────

class TimeMap:
    """원본 영상 시간 ↔ 컷 편집된 영상 시간."""

    def __init__(self, segments: list[tuple[float, float]]):
        self.segments = segments
        self.offsets = []
        acc = 0.0
        for a, b in segments:
            self.offsets.append(acc)
            acc += b - a
        self.total = acc

    def to_cut(self, t: float) -> float | None:
        for (a, b), off in zip(self.segments, self.offsets):
            if a <= t <= b:
                return off + (t - a)
        return None

    def remap_words(self, words: list[Word], cut_idx: dict[int, str]) -> list[Word]:
        out = []
        for i, w in enumerate(words):
            if i in cut_idx:
                continue
            s, e = self.to_cut(w.start), self.to_cut(w.end)
            if s is None and e is None:
                mid = self.to_cut((w.start + w.end) / 2)
                if mid is None:
                    continue
                s = e = mid
            s = e if s is None else s
            e = s if e is None else e
            out.append(Word(round(s, 3), round(max(e, s), 3), w.text, w.prob))
        return out


# ───────────────────────── 렌더링 ─────────────────────────

def render_cut(src: Path, dst: Path, segments: list[tuple[float, float]], info: VideoInfo,
               cq: int, work_dir: Path, log=print, audio_fade: float = 0.015, x264_preset: str = "medium") -> None:
    # 구간 [a, b) 의 프레임만 고른다. 반 프레임 당겨서 비교해야 끝 프레임이 하나 더 들어가지 않는다
    # (프레임 수 = 오디오 길이와 정확히 일치 → 구간이 많아도 싱크가 밀리지 않음)
    h = 0.5 / info.fps
    expr = "+".join(f"between(t,{a - h:.5f},{b - h:.5f})" for a, b in segments)
    parts = [f"[0:v]fps={info.fps:.5f},select='{expr}',setpts=N/FRAME_RATE/TB[v]"]
    maps = ["-map", "[v]"]
    if info.has_audio:
        # 오디오는 구간마다 잘라 아주 짧게 페이드 인/아웃한 뒤 이어붙인다 → 컷 경계의 '틱' 소리 방지
        n = len(segments)
        labels = "".join(f"[as{i}]" for i in range(n))
        parts.append(f"[0:a]asplit={n}{labels}" if n > 1 else "[0:a]anull[as0]")
        for i, (a, b) in enumerate(segments):
            d = min(audio_fade, (b - a) / 4)
            parts.append(f"[as{i}]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={d:.4f},afade=t=out:st={b - a - d:.4f}:d={d:.4f}[ac{i}]")
        parts.append("".join(f"[ac{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]")
        maps += ["-map", "[a]"]
    script = work_dir / "cut_filter.txt"
    script.write_text(";\n".join(parts), encoding="utf-8")
    log(f"[컷] {len(segments)}개 구간을 이어붙여 렌더링 중...")
    run_ffmpeg(["-i", str(src), *filter_script_args(script), *maps,
                *video_encoder_args(max(cq - 2, 14), x264_preset), "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(dst)], log)

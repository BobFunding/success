from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path

from .config import PROJECT_DIR, Settings, load_dotenv
from .correct import correct_transcript
from .cutter import (TimeMap, compute_keep_segments, decide_fillers, detect_silences, render_cut,
                     snap_to_frames)
from .ffmpeg_utils import extract_audio, probe
from .illustrate import make_illustrations, place_cards
from .llm import LLM
from .privacy import detect_screen_pii, detect_spoken_pii, regex_pii
from .render import render_final
from .transcribe import Word, group_sentences, transcribe


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def subtitle_cues(words: list[Word], beeps: list[dict], max_chars: int = 22,
                  min_show: float = 0.8) -> list[tuple[float, float, str]]:
    """자막 조각 만들기: 문장 단위로 나눈 뒤 긴 문장은 비슷한 길이로 쪼개고, 삐- 처리된 말은 자막에서도 가린다."""
    texts = []
    for w in words:
        mid = (w.start + w.end) / 2
        hidden = any(b["start"] <= mid <= b["end"] for b in beeps)
        texts.append("(삐-)" if hidden else w.text)
    # 연속된 (삐-) 는 하나로 합치고, 삐- 소리가 나는 동안 계속 보이도록 끝 시각을 늘린다
    shown: list[Word] = []
    for i, (w, t) in enumerate(zip(words, texts)):
        if t == "(삐-)" and i > 0 and texts[i - 1] == "(삐-)":
            shown[-1].end = w.end
        else:
            shown.append(Word(w.start, w.end, t, w.prob))

    cues: list[tuple[float, float, str]] = []
    for sent in group_sentences(shown, max_gap=0.6, max_chars=10_000):
        a, b = sent["word_range"]
        idx = list(range(a, b + 1))
        total = len(sent["text"])
        n = max(1, math.ceil(total / max_chars))
        target = total / n
        chunk: list[int] = []
        for k, i in enumerate(idx):
            chunk.append(i)
            length = sum(len(shown[j].text) + 1 for j in chunk)
            rest = len(idx) - k - 1
            # 목표 길이에 닿았거나, 쉼표에서 적당히 찼으면 끊는다 (마지막 조각이 너무 짧지 않게)
            if rest and (length >= target or (shown[i].text.endswith(",") and length >= target * 0.6)):
                cues.append((shown[chunk[0]].start, shown[chunk[-1]].end, " ".join(shown[j].text for j in chunk)))
                chunk = []
        if chunk:
            cues.append((shown[chunk[0]].start, shown[chunk[-1]].end, " ".join(shown[j].text for j in chunk)))

    # 너무 짧게 스쳐 지나가는 자막은 다음 자막 직전까지 늘려서 읽을 시간을 준다
    out = []
    for k, (s, e, t) in enumerate(cues):
        nxt = cues[k + 1][0] if k + 1 < len(cues) else e + min_show
        out.append((s, max(e, min(s + min_show, nxt)), t))
    return out


def write_srt(words: list[Word], beeps: list[dict], path: Path) -> None:
    def ts(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"

    lines = []
    for n, (s, e, text) in enumerate(subtitle_cues(words, beeps), 1):
        lines += [str(n), f"{ts(s)} --> {ts(e)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(video: str | Path, settings: Settings | None = None, out_root: Path | None = None, log=print) -> Path:
    load_dotenv()
    settings = settings or Settings()
    video = Path(video)
    out_root = out_root or PROJECT_DIR / "output"
    work = out_root / f"{video.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    info = probe(video)
    log(f"[시작] {video.name}  {info.width}x{info.height}  {info.fps:.2f}fps  {_fmt(info.duration)}")
    llm = LLM(settings.model, log)

    # ── 1. 받아쓰기 ──
    wav = work / "audio_16k.wav"
    words: list[Word] = []
    fixes: list[dict] = []
    if info.has_audio:
        extract_audio(video, wav)
        words = transcribe(wav, settings.whisper_model, settings.language, settings.vocabulary, log)
        if settings.transcript_correction:
            words, fixes = correct_transcript(words, settings.vocabulary, llm, log)
    else:
        log("[받아쓰기] 오디오가 없는 영상입니다. 컷 편집·일러스트·말소리 검사는 건너뜁니다.")
    (work / "transcript_original.json").write_text(
        json.dumps([w.to_dict() for w in words], ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 2. 1차 컷 편집 ──
    cut_idx: dict[int, str] = {}
    segments: list[tuple[float, float]] = []
    if settings.cut_enabled and words:
        cut_idx = decide_fillers(words, llm if settings.llm_filler_review else None, log)
        silences = detect_silences(wav, settings.max_pause)
        segments = compute_keep_segments(words, cut_idx, silences, info.duration,
                                         settings.pad, settings.max_pause, settings.min_segment)
        segments = snap_to_frames(segments, info.fps)
        if not segments:  # 전부 필러/무음으로 판정된 경우 → 다 자르면 빈 영상이 되므로 컷하지 않는다
            log("[컷] 남길 구간이 없어 컷 편집을 건너뜁니다.")
            cut_idx = {}
    cut_video = work / "1_cut.mp4"
    if segments:
        render_cut(video, cut_video, segments, info, settings.quality_cq, work, log, settings.audio_crossfade)
    else:
        segments = [(0.0, info.duration)]
        shutil.copy(video, cut_video)
    tmap = TimeMap(segments)
    cut_words = tmap.remap_words(words, cut_idx)
    cut_info = probe(cut_video)
    log(f"[컷] {_fmt(info.duration)} → {_fmt(cut_info.duration)} "
        f"({info.duration - cut_info.duration:.1f}초 단축)")
    (work / "transcript_cut.json").write_text(
        json.dumps([w.to_dict() for w in cut_words], ensure_ascii=False, indent=1), encoding="utf-8")
    sentences = group_sentences(cut_words)

    # ── 3. 개인정보 감지 ──
    mosaics, beeps, text_boxes = [], [], []
    if settings.privacy_enabled:
        mosaics, text_boxes = detect_screen_pii(cut_video, settings.ocr_interval, llm, settings.privacy_allowlist,
                                    cut_info.width, cut_info.height, log)
        (work / "ocr_text_boxes.json").write_text(json.dumps(text_boxes), encoding="utf-8")
        if settings.beep_spoken_pii and cut_words:
            beeps = detect_spoken_pii(cut_words, llm, settings.privacy_allowlist, log)
    if cut_words:  # 개인정보 감지 뒤에 써야 삐- 처리한 말이 자막에 남지 않는다
        write_srt(cut_words, [b.to_dict() for b in beeps], work / "subtitles.srt")

    # ── 4. 설명 일러스트 ──
    inserts = []
    if settings.illustrations_enabled and sentences:
        inserts = make_illustrations(sentences, cut_info.duration, llm, cut_info.width, cut_info.height,
                                     work / "illustrations", settings, log)
        place_cards(inserts, text_boxes, cut_info.width, cut_info.height)

    # ── 5. 편집 계획 저장 → 최종 렌더링 ──
    plan = {
        "source": str(video),
        "settings": settings.to_dict(),
        "mosaics": [m.to_dict() for m in mosaics],
        "beeps": [b.to_dict() for b in beeps],
        "inserts": [i.to_dict() for i in inserts],
    }
    plan_path = work / "edit_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    final = render_from_plan(work, log)

    write_report(work, video, info.duration, cut_info.duration, words, cut_idx, segments, plan, time.time() - t0,
                 fixes)
    log(f"[완료] {final}  (총 {time.time() - t0:.0f}초)")
    return work


def render_from_plan(work: Path, log=print) -> Path:
    """edit_plan.json 을 직접 고친 뒤(오탐 모자이크 삭제, 일러스트 시간 조정 등) 최종본만 다시 뽑을 때 사용."""
    plan = json.loads((work / "edit_plan.json").read_text(encoding="utf-8"))
    settings = Settings(**plan["settings"])
    cut_video = work / "1_cut.mp4"
    info = probe(cut_video)
    final = work / "2_final.mp4"
    render_final(cut_video, final, info, plan["mosaics"], plan["beeps"], plan["inserts"],
                 settings.mosaic_block, settings.quality_cq, work, log,
                 fx={"fade_in": settings.fade_in, "fade_out": settings.fade_out,
                     "card_slide": settings.card_slide, "full_zoom": settings.full_zoom})
    # 삐- 목록을 고쳤을 수 있으므로 자막도 다시 쓴다
    transcript = work / "transcript_cut.json"
    if transcript.exists():
        words = [Word(**w) for w in json.loads(transcript.read_text(encoding="utf-8"))]
        if words:
            write_srt(words, plan["beeps"], work / "subtitles.srt")
    return final


def write_report(work: Path, video: Path, before: float, after: float, words: list[Word],
                 cut_idx: dict[int, str], segments, plan: dict, elapsed: float, fixes: list[dict]) -> None:
    L = [f"# 편집 리포트 — {video.name}", "",
         f"- 원본 길이: {_fmt(before)} → 컷 편집 후: {_fmt(after)} (−{before - after:.1f}초)",
         f"- 받아쓰기 교정: {len(fixes)}개",
         f"- 남긴 구간: {len(segments)}개 / 잘라낸 필러·말더듬: {len(cut_idx)}개",
         f"- 설명 일러스트: {len(plan['inserts'])}장 / 화면 모자이크: {len(plan['mosaics'])}건 / 삐- 처리: {len(plan['beeps'])}건",
         f"- 처리 시간: {elapsed:.0f}초", "",
         "## 결과 파일",
         "- `1_cut.mp4` — 1차 컷 편집본 (무음·필러 제거만)",
         "- `2_final.mp4` — 일러스트 + 모자이크까지 적용된 최종본",
         "- `subtitles.srt` — 컷 편집본 기준 자막",
         "- `edit_plan.json` — 모자이크/삐-/일러스트 목록. 고친 뒤 `python run.py --rerender <이 폴더>` 로 다시 렌더링", ""]

    L += ["## 설명 일러스트 (최종본 시간 기준)", ""]
    for i in plan["inserts"]:
        L.append(f"- {_fmt(i['start'])}~{_fmt(i['end'])} [{i['placement']}] {i['concept']}"
                 + (f" — 글자: \"{i['label']}\"" if i["label"] else "")
                 + f"  (`{Path(i['png_path']).name}`)")
    L += ["", "## 개인정보 처리 — 꼭 직접 확인하세요", "",
          "자동 감지는 놓치는 경우가 있습니다. 업로드 전 최종본을 한 번 훑어봐 주세요.", ""]
    for m in plan["mosaics"]:
        L.append(f"- 화면 {_fmt(m['start'])}~{_fmt(m['end'])} {m['kind']}: {_mask(m['text'])}")
    for b in plan["beeps"]:
        L.append(f"- 음성 {_fmt(b['start'])}~{_fmt(b['end'])} {b['kind']}: {_mask(b['text'])}")
    L += ["", "## 받아쓰기 교정 (원본 시간 기준) — 자막이 이상하면 여기부터 확인", ""]
    for f in fixes:
        # 교정 전후 어느 쪽이든 개인정보처럼 보이면 리포트에도 가려서 남긴다
        hide = regex_pii(f["before"]) or regex_pii(f["after"])
        before, after = (_mask(f["before"]), _mask(f["after"])) if hide else (f["before"], f["after"])
        L.append(f"- {_fmt(f['start'])} \"{before}\" → \"{after}\" — {f['reason']}")
    L += ["", "## 잘라낸 필러·말더듬 (원본 시간 기준)", ""]
    for i in sorted(cut_idx):
        w = words[i]
        L.append(f"- {_fmt(w.start)} \"{w.text}\" — {cut_idx[i]}")
    (work / "report.md").write_text("\n".join(L), encoding="utf-8")


def _mask(text: str) -> str:
    """리포트에도 개인정보가 그대로 남지 않도록 가운데를 가린다."""
    t = text.strip()
    if len(t) <= 2:
        return t[0] + "*" if t else t
    keep = max(1, len(t) // 4)
    return t[:keep] + "*" * (len(t) - 2 * keep) + t[-keep:]

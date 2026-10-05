from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .config import PROJECT_DIR, Settings, load_dotenv
from .cutter import TimeMap, compute_keep_segments, decide_fillers, detect_silences, render_cut
from .ffmpeg_utils import extract_audio, probe
from .illustrate import make_illustrations
from .llm import LLM
from .privacy import detect_screen_pii, detect_spoken_pii
from .render import render_final
from .transcribe import Word, group_sentences, transcribe


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def write_srt(words: list[Word], path: Path) -> None:
    def ts(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"

    lines, n = [], 0
    for sent in group_sentences(words, max_gap=0.6, max_chars=24):
        n += 1
        lines += [str(n), f"{ts(sent['start'])} --> {ts(sent['end'])}", sent["text"], ""]
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
    if info.has_audio:
        extract_audio(video, wav)
        words = transcribe(wav, settings.whisper_model, settings.language, log)
    else:
        log("[받아쓰기] 오디오가 없는 영상입니다. 컷 편집·일러스트·말소리 검사는 건너뜁니다.")
    (work / "transcript_original.json").write_text(
        json.dumps([w.to_dict() for w in words], ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 2. 1차 컷 편집 ──
    cut_idx: dict[int, str] = {}
    if settings.cut_enabled and words:
        cut_idx = decide_fillers(words, llm if settings.llm_filler_review else None, log)
        silences = detect_silences(wav, settings.max_pause)
        segments = compute_keep_segments(words, cut_idx, silences, info.duration,
                                         settings.pad, settings.max_pause, settings.min_segment)
        cut_video = work / "1_cut.mp4"
        render_cut(video, cut_video, segments, info, settings.quality_cq, work, log)
    else:
        segments = [(0.0, info.duration)]
        cut_video = work / "1_cut.mp4"
        shutil.copy(video, cut_video)
    tmap = TimeMap(segments)
    cut_words = tmap.remap_words(words, cut_idx)
    cut_info = probe(cut_video)
    log(f"[컷] {_fmt(info.duration)} → {_fmt(cut_info.duration)} "
        f"({info.duration - cut_info.duration:.1f}초 단축)")
    (work / "transcript_cut.json").write_text(
        json.dumps([w.to_dict() for w in cut_words], ensure_ascii=False, indent=1), encoding="utf-8")
    if cut_words:
        write_srt(cut_words, work / "subtitles.srt")
    sentences = group_sentences(cut_words)

    # ── 3. 개인정보 감지 ──
    mosaics, beeps = [], []
    if settings.privacy_enabled:
        mosaics = detect_screen_pii(cut_video, settings.ocr_interval, llm, settings.privacy_allowlist,
                                    cut_info.width, cut_info.height, log)
        if settings.beep_spoken_pii and cut_words:
            beeps = detect_spoken_pii(cut_words, llm, settings.privacy_allowlist, log)

    # ── 4. 설명 일러스트 ──
    inserts = []
    if settings.illustrations_enabled and sentences:
        inserts = make_illustrations(sentences, cut_info.duration, llm, cut_info.width, cut_info.height,
                                     work / "illustrations", settings, log)

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

    write_report(work, video, info.duration, cut_info.duration, words, cut_idx, segments, plan, time.time() - t0)
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
                 settings.mosaic_block, settings.quality_cq, work, log)
    return final


def write_report(work: Path, video: Path, before: float, after: float, words: list[Word],
                 cut_idx: dict[int, str], segments, plan: dict, elapsed: float) -> None:
    L = [f"# 편집 리포트 — {video.name}", "",
         f"- 원본 길이: {_fmt(before)} → 컷 편집 후: {_fmt(after)} (−{before - after:.1f}초)",
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

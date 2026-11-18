"""다국어 (DESIGN.md 8.4): 번역 보관과 언어별 결과물(자막·제목·설명·음성 트랙).

번역은 작업 폴더 translations.json 에 언어별로: {"en": {"제목": ..., "설명": ..., "단계1": ..., "<문장 키>": ...}}.
AI 도우미가 채우거나(assistant.translate) 사람이 화면에서 직접 적는다. 영상에 새긴 자막은 한국어 그대로이고,
다른 언어는 따로 올리는 자막 파일·음성 트랙·글로 나간다(유튜브 다국어 자막·음성, 웹 VTT·언어별 페이지).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..ffmpeg_utils import FFMPEG

LANGS = {"en": "English", "ja": "日本語", "zh": "中文", "vi": "Tiếng Việt", "es": "Español", "fr": "Français",
         "de": "Deutsch", "id": "Bahasa Indonesia", "th": "ไทย"}


def path(work: Path) -> Path:
    return work / "translations.json"


def load(work: Path) -> dict[str, dict[str, str]]:
    try:
        d = json.loads(path(work).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if k in LANGS and isinstance(v, dict)}
    except Exception:
        return {}


def save(work: Path, lang: str, items: dict[str, str]) -> dict:
    if lang not in LANGS:
        raise ValueError("모르는 언어예요.")
    d = load(work)
    d[lang] = {str(k): str(v).strip() for k, v in items.items() if str(v).strip()}
    if not d[lang]:
        d.pop(lang)
    path(work).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def source(sc) -> dict[str, str]:
    """번역할 한국어: 제목·설명·단계 이름·문장 전부(키 → 글)."""
    from . import sentences as T
    topic = T.topic_words(sc.title_plain.split(",")[0])
    out = {"제목": sc.title_plain, "설명": f"{topic} 방법을 {T.count_word(len(sc.steps))} 단계로 알려 드려요."}
    out.update({f"단계{i + 1}": s for i, s in enumerate(sc.steps)})
    out.update({l.key: l.text for l in sc.lines()})
    return out


def missing(sc, tr: dict[str, str]) -> list[str]:
    return [k for k in source(sc) if not tr.get(k)]


def srt(tl: dict, tr: dict[str, str], out: Path) -> Path:
    """만들기 때의 시각표(timeline.json)에 번역 문장을 얹은 자막. 번역이 빈 문장은 건너뜀."""
    from .compose import srt_time
    rows, i = [], 1
    for x in tl["lines"]:
        t = tr.get(x["key"])
        if not t:
            continue
        rows += [str(i), f"{srt_time(x['t'])} --> {srt_time(x['t'] + x['dur'])}", t, ""]
        i += 1
    out.write_text("\n".join(rows), encoding="utf-8")
    return out


def spoken(text: str) -> str:
    """읽을 글: 자막에 함께 둔 화면 글자(한국어 괄호)는 소리로는 빼고, 남는 빈칸·쉼표를 정리."""
    import re
    t = re.sub(r"\s*\([^()]*[가-힣][^()]*\)", "", text)
    return re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s{2,}", " ", t)).strip()


def voice_track(tl: dict, tr: dict[str, str], lang: str, out: Path, work: Path, log=print) -> Path:
    """그 언어 목소리로 문장마다 읽어 한국어 문장과 같은 때에 놓은 음성 트랙(유튜브 '오디오 트랙 추가'용, 영상과 길이 같음).
    번역 문장이 자리보다 길면 조금 빠르게(최대 1.35배) 읽는다."""
    from ..narration import Line, build_track
    from .voices import LANG_VOICES, synthesize
    voice, rate = LANG_VOICES[lang]
    keys = [x for x in tl["lines"] if tr.get(x["key"])]
    d = work / "narration_lang" / lang
    lines = [Line(x["key"], spoken(tr[x["key"]])) for x in keys]
    synthesize(lines, work, d.resolve(), voice, rate, log=log)
    placed = []
    for i, (x, ln) in enumerate(zip(keys, lines)):
        nxt = keys[i + 1]["t"] if i + 1 < len(keys) else tl["total"]
        slot = max(0.8, nxt - x["t"] - 0.15)
        wav = ln.path
        if ln.duration > slot:
            k = min(1.35, ln.duration / slot)
            fast = Path(ln.path).with_name(f"{ln.key}.fast.wav")
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", ln.path, "-af", f"atempo={k:.3f}", str(fast)], check=True)
            wav = str(fast)
        placed.append((x["t"], wav))
    tmp = out.with_suffix(".wav")
    build_track(placed, tl["total"], tmp)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(tmp), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-metadata:s:a:0", f"language={ISO3.get(lang, lang)}", str(out)], check=True)
    tmp.unlink(missing_ok=True)
    return out


ISO3 = {"en": "eng", "ja": "jpn", "zh": "zho", "vi": "vie", "es": "spa", "fr": "fra", "de": "deu", "id": "ind", "th": "tha"}

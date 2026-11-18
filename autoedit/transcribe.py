from __future__ import annotations

import os
import wave
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


# Whisper 는 "어", "음" 같은 말버릇을 지워버리는 경향이 있어서,
# 프롬프트에 필러가 들어간 문장을 주면 그대로 받아적을 확률이 올라간다.
FILLER_PROMPT = "음... 어, 그러니까 어 이게 음 뭐냐면, 아 네 그래서 어어 이렇게 하면 돼요."


def _add_cuda_dll_dirs() -> None:
    """Windows 에서 faster-whisper(CTranslate2)가 cuBLAS/cuDNN DLL 을 찾도록 torch 의 lib 폴더를 등록."""
    if os.name != "nt":
        return
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.exists():
            os.add_dll_directory(str(lib))
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


# 영어 구간용 필러 프롬프트 (한국어 프롬프트를 영어 구간에 주면 번역해서 받아 적는 경우가 있음)
FILLER_PROMPT_EN = "Um, so, uh, like, you know, I mean, uh, it's kind of, um, yeah."


@dataclass
class _Seg:
    start: float
    end: float
    logprob: float
    words: list[Word]


def merge_language_passes(passes: dict[str, list[_Seg]], min_overlap: float = 0.3) -> list[Word]:
    """언어별로 따로 받아 적은 결과를 합친다. 확신도(avg_logprob)가 높은 구간부터 차지하고,
    이미 차지한 구간과 많이 겹치는 구간은 버린다 → 구간마다 그 언어로 더 잘 들린 쪽이 남는다.
    (한 번에 언어를 섞어 받아 적게 하면 영어를 한국어로 번역해 지어내거나 구간을 건너뛰는 일이 잦다)"""
    candidates = sorted((seg for segs in passes.values() for seg in segs), key=lambda s: -s.logprob)
    taken: list[_Seg] = []
    for seg in candidates:
        dur = max(seg.end - seg.start, 1e-3)
        overlap = sum(max(0.0, min(seg.end, t.end) - max(seg.start, t.start)) for t in taken)
        if overlap / dur < min_overlap:
            taken.append(seg)
    words: list[Word] = []
    for seg in sorted(taken, key=lambda s: s.start):
        for w in seg.words:
            mid = (w.start + w.end) / 2
            # 살짝 겹친 가장자리 단어는 먼저 차지한(확신도 높은) 구간 쪽만 남긴다
            owner = max((t for t in taken if t.start <= mid <= t.end), key=lambda t: t.logprob, default=seg)
            if owner is seg and (not words or w.start >= words[-1].start):
                words.append(w)
    return words


def _prompt_for(lang: str, vocabulary: list[str] | None) -> str | None:
    topic = f" {', '.join(vocabulary)}." if vocabulary else ""
    if lang == "ko":
        return FILLER_PROMPT + (f" 오늘 주제:{topic}" if topic else "")
    if lang == "en":
        return FILLER_PROMPT_EN + topic
    return topic.strip() or None


def _has_cuda() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_engine(engine: str) -> str:
    """받아쓰기 방식 고르기. auto: GPU 가 있으면 PC(faster-whisper, 무료),
    GPU 가 없는 컴퓨터(클라우드 VM 등)에 OpenAI 키가 있으면 OpenAI Whisper API(정확도↑, 분당 약 0.006달러)."""
    if engine in ("local", "openai"):
        return engine
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return "openai" if has_key else "local"
    return "openai" if has_key and not _has_cuda() else "local"


API_CHUNK_SEC = 600          # 16kHz mono wav 10분 ≈ 19MB (API 파일 한도 25MB)


def segs_from_api(resp: dict, offset: float = 0.0) -> list[_Seg]:
    """OpenAI 받아쓰기 응답(verbose_json, 단어·구간 타임스탬프)을 _Seg 목록으로 바꾼다.
    단어는 응답 맨 위에 따로 오므로 시간으로 구간에 나눠 담는다(구간 확신도는 언어 합치기에 씀)."""
    segs = [_Seg(offset + s["start"], offset + s["end"], s.get("avg_logprob", 0.0), [])
            for s in resp.get("segments") or []]
    if not segs:
        segs = [_Seg(offset, offset + float(resp.get("duration") or 0), 0.0, [])]
    k = 0
    for w in resp.get("words") or []:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        word = Word(round(offset + w["start"], 3), round(offset + w["end"], 3), text, 1.0)
        mid = (word.start + word.end) / 2
        while k + 1 < len(segs) and mid >= segs[k + 1].start:
            k += 1
        segs[k].words.append(word)
    return [s for s in segs if s.words]


def transcribe_api(audio: np.ndarray, languages: list[str], vocabulary: list[str] | None = None,
                   log=print, client=None, sr: int = 16000) -> list[Word]:
    """OpenAI Whisper API(whisper-1)로 받아쓰기. GPU 없는 VM 에서 CPU 로 큰 모델을 돌리는 것보다 빠르고 정확하다.
    긴 영상은 10분씩 나눠 보내고 시간을 이어 붙인다."""
    import io
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    duration = len(audio) / sr
    step = API_CHUNK_SEC * sr
    passes: dict[str, list[_Seg]] = {}
    for lang in languages:
        segs: list[_Seg] = []
        for i in range(0, max(len(audio), 1), step):
            piece = (np.clip(audio[i:i + step], -1, 1) * 32767).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(piece.tobytes())
            buf.seek(0)
            buf.name = "audio.wav"
            r = client.audio.transcriptions.create(
                model="whisper-1", file=buf, language=lang, prompt=_prompt_for(lang, vocabulary),
                response_format="verbose_json", timestamp_granularities=["word", "segment"])
            resp = r.model_dump() if hasattr(r, "model_dump") else dict(r)
            segs += segs_from_api(resp, offset=i / sr)
            log(f"[받아쓰기] ({lang}, OpenAI API) {min((i + step) / sr, duration):7.1f}s / {duration:.1f}s")
        passes[lang] = segs
    if len(passes) == 1:
        return [w for seg in next(iter(passes.values())) for w in seg.words]
    words = merge_language_passes(passes)
    log(f"[받아쓰기] {'+'.join(languages)} 결과를 구간별로 합침: 단어 {len(words)}개")
    return words


def transcribe(audio_path: Path, model_name: str, language: str, vocabulary: list[str] | None = None,
               log=print, engine: str = "local") -> list[Word]:
    """language: "ko" 처럼 하나, 또는 "ko+en" 처럼 여러 개(언어마다 받아 적고 구간별로 더 잘 들린 쪽을 고름).
    engine: local(faster-whisper) / openai(Whisper API) / auto(GPU 없고 OpenAI 키 있으면 API)."""
    engine = resolve_engine(engine)
    if engine == "openai":
        with wave.open(str(audio_path), "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        langs = [x.strip() for x in language.split("+") if x.strip()] or ["ko"]
        log("[받아쓰기] OpenAI Whisper API(whisper-1) 사용 — GPU 없는 환경용, 분당 약 0.006달러")
        return transcribe_api(audio, langs, vocabulary, log)
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    # 16kHz mono wav 를 직접 읽어서 넘긴다 (faster-whisper 내부 디코더가 최신 PyAV 와 호환되지 않는 경우가 있음)
    with wave.open(str(audio_path), "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    languages = [x.strip() for x in language.split("+") if x.strip()] or ["ko"]
    attempts = [("cuda", "float16"), ("cpu", "int8")]
    last_error = None
    for device, compute_type in attempts:
        try:
            log(f"[받아쓰기] Whisper {model_name} 로딩 ({device})...")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            passes: dict[str, list[_Seg]] = {}
            for lang in languages:
                prompt = _prompt_for(lang, vocabulary)
                segments, info = model.transcribe(
                    audio,
                    language=lang,
                    word_timestamps=True,
                    # 주제 용어는 초기 프롬프트에도 넣는다 (hotwords 만으로는 "단리"→[달리] 같은 발음 변화를 못 이김)
                    initial_prompt=prompt,
                    condition_on_previous_text=False,
                    vad_filter=False,  # VAD 를 켜면 짧은 필러가 같이 날아간다
                    beam_size=5,
                    # 영상 주제 용어를 알려주면 "단리"를 "달리"로 듣는 식의 오류가 줄어든다
                    hotwords=" ".join(vocabulary) if vocabulary else None,
                )
                segs: list[_Seg] = []
                for seg in segments:
                    words = [Word(round(w.start, 3), round(w.end, 3), w.word.strip(), round(w.probability, 3))
                             for w in seg.words or [] if w.word.strip()]
                    if words:
                        segs.append(_Seg(seg.start, seg.end, seg.avg_logprob, words))
                    log(f"[받아쓰기] ({lang}) {seg.end:7.1f}s / {info.duration:.1f}s  {seg.text.strip()[:40]}")
                passes[lang] = segs
            if len(passes) == 1:
                return [w for seg in next(iter(passes.values())) for w in seg.words]
            words = merge_language_passes(passes)
            log(f"[받아쓰기] {'+'.join(languages)} 결과를 구간별로 합침: 단어 {len(words)}개")
            return words
        except Exception as e:  # CUDA DLL 문제 등은 실제 추론 시점에 터지는 경우가 많다
            last_error = e
            log(f"[받아쓰기] {device} 실패: {e}")
    raise RuntimeError(f"받아쓰기 실패: {last_error}")


def group_sentences(words: list[Word], max_gap: float = 0.8, max_chars: int = 60) -> list[dict]:
    """단어를 문장(자막 한 줄) 단위로 묶는다. 일러스트 기획·개인정보 판단에 쓰인다."""
    sentences: list[dict] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]
            text_len = sum(len(words[j].text) + 1 for j in cur)
            if w.start - prev.end > max_gap or text_len > max_chars or prev.text.endswith((".", "?", "!")):
                sentences.append(_sentence(words, cur))
                cur = []
        cur.append(i)
    if cur:
        sentences.append(_sentence(words, cur))
    return sentences


def _sentence(words: list[Word], idx: list[int]) -> dict:
    return {
        "start": words[idx[0]].start,
        "end": words[idx[-1]].end,
        "text": " ".join(words[i].text for i in idx),
        "word_range": [idx[0], idx[-1]],
    }

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


def transcribe(audio_path: Path, model_name: str, language: str, log=print) -> list[Word]:
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    # 16kHz mono wav 를 직접 읽어서 넘긴다 (faster-whisper 내부 디코더가 최신 PyAV 와 호환되지 않는 경우가 있음)
    with wave.open(str(audio_path), "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    attempts = [("cuda", "float16"), ("cpu", "int8")]
    last_error = None
    for device, compute_type in attempts:
        try:
            log(f"[받아쓰기] Whisper {model_name} 로딩 ({device})...")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            segments, info = model.transcribe(
                audio,
                language=language,
                word_timestamps=True,
                initial_prompt=FILLER_PROMPT,
                condition_on_previous_text=False,
                vad_filter=False,  # VAD 를 켜면 짧은 필러가 같이 날아간다
                beam_size=5,
            )
            words: list[Word] = []
            for seg in segments:
                for w in seg.words or []:
                    text = w.word.strip()
                    if text:
                        words.append(Word(round(w.start, 3), round(w.end, 3), text, round(w.probability, 3)))
                log(f"[받아쓰기] {seg.end:7.1f}s / {info.duration:.1f}s  {seg.text.strip()[:40]}")
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

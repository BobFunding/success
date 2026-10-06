"""AI 나레이션 생성: 대본을 문장별로 음성 합성하고, 다듬어서 문장별 파일과 길이를 돌려준다.

기존 파이프라인과 별개로 동작한다(다른 모듈을 고치거나 부르지 않음). 음성은 edge-tts
(Microsoft 신경망 음성, API 키 불필요). 상업적 사용 전 이용 조건을 확인할 것.

발음 팁 (받아쓰기로 확인함)
- "태권월드"는 가끔 "태권널드"로 들린다 → 대본에 "태권 월드"로 띄어 쓴다.
- 숨 쉬는 자리에 쉼표를 넣으면 끊어 읽기가 자연스러워진다.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg_utils import FFMPEG

VOICE = "ko-KR-HyunsuMultilingualNeural"   # 사용자가 고른 목소리 (현수, 차분 버전)
RATE = -8                                  # 기본 속도(%) — 따라 하는 튜토리얼용으로 차분하게

# 편안한 중저음(280Hz 살짝↑), 끝음절이 또렷하게(3.5kHz↑), 여린 끝을 끌어올리는 압축, 유튜브 음량(-14 LUFS)
VOICE_CHAIN = ("highpass=f=80,equalizer=f=280:t=q:w=1.0:g=1.2,equalizer=f=3500:t=q:w=1.2:g=2,"
               "equalizer=f=9000:t=q:w=1.5:g=1,"
               "acompressor=threshold=-30dB:ratio=3:attack=5:release=80:makeup=2,alimiter=limit=0.9")


@dataclass
class Line:
    key: str
    text: str
    rate: int = 0          # 문장마다 속도·높낮이를 조금씩 달리하면 기계적인 느낌이 줄어든다
    pitch: int = 0
    path: str = ""
    duration: float = 0.0


def _use_proxy_ca() -> None:
    """이 환경처럼 보안 프록시가 TLS 를 다시 맺는 곳에서는 프록시 CA 묶음을 신뢰하게 한다(검증은 유지)."""
    bundle = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
    if Path(bundle).exists():
        import certifi
        certifi.where = lambda: bundle


def synthesize(lines: list[Line], out_dir: Path, voice: str = VOICE, base_rate: int = RATE, log=print) -> list[Line]:
    """문장별 wav(48kHz mono)를 만들고 길이를 채워 돌려준다. 앞뒤 완전 무음만 정리하고 끝음절 꼬리는 살린다."""
    _use_proxy_ca()
    import edge_tts

    out_dir.mkdir(parents=True, exist_ok=True)

    async def one(ln: Line):
        raw = out_dir / f"{ln.key}.raw.mp3"
        await edge_tts.Communicate(ln.text, voice, rate=f"{base_rate + ln.rate:+d}%",
                                   pitch=f"{ln.pitch:+d}Hz").save(str(raw))
        return raw

    async def all_():
        return await asyncio.gather(*[one(ln) for ln in lines])

    raws = asyncio.run(all_())
    for ln, raw in zip(lines, raws):
        wav = out_dir / f"{ln.key}.wav"
        trim = ("silenceremove=start_periods=1:start_threshold=-65dB:start_silence=0.05,areverse,"
                "silenceremove=start_periods=1:start_threshold=-65dB:start_silence=0.12,areverse")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(raw), "-af", f"{trim},{VOICE_CHAIN}",
                        "-ar", "48000", "-ac", "1", str(wav)], check=True)
        ln.path = str(wav)
        ln.duration = _duration(wav)
    log(f"[나레이션] {len(lines)}문장, 말 {sum(l.duration for l in lines):.1f}초")
    return lines


def _duration(path: Path) -> float:
    import wave
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def build_track(placed: list[tuple[float, str]], total: float, out: Path, room_tone: bool = True) -> None:
    """(시작 초, wav) 목록을 한 트랙으로 배치한다. 문장 사이는 아주 작은 방 소리로 채워 디지털 무음 느낌을 없앤다.
    마지막에 음량을 유튜브 기준(-14 LUFS)으로 맞춘다."""
    inputs, parts = [], []
    for i, (t, wav) in enumerate(placed):
        inputs += ["-i", wav]
        ms = int(round(t * 1000))
        parts.append(f"[{i}]adelay={ms}|{ms},apad[a{i}]")
    n = len(placed)
    mix = "".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:duration=longest:normalize=0,atrim=0:{total:.3f}"
    graph = ";".join(parts) + ";" + mix + "[v]"
    if room_tone:
        graph += (f";anoisesrc=color=pink:amplitude=0.0012:sample_rate=48000:duration={total:.3f},"
                  "lowpass=f=5000,highpass=f=120[room];[v][room]amix=inputs=2:duration=first:normalize=0[m]")
        last = "[m]"
    else:
        last = "[v]"
    graph += f";{last}loudnorm=I=-14:TP=-1.5:LRA=7[out]"
    subprocess.run([FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(out)], check=True)

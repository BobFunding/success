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
# 받아 오는 목소리는 24kHz·48kbps mp3 라 높은 음역에 압축 잡음이 있다. 높은 음을 키우면 'ㅅ·ㅈ·ㅊ'에서 지지직이 커진다
# (2026-10-13 사용자 지적) → 높은 음은 키우지 않고, 치찰음은 눌러 주고, 10kHz 위(압축 잡음 자리)는 걷어 낸다.
VOICE_CHAIN = ("highpass=f=80,equalizer=f=280:t=q:w=1.0:g=1.2,equalizer=f=2800:t=q:w=1.4:g=0.8,"
               "deesser=i=0.35:m=0.5:f=0.5,lowpass=f=10000:p=2,"
               "acompressor=threshold=-30dB:ratio=2.5:attack=12:release=150:makeup=2,alimiter=limit=0.9")


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


def _edge_hosts() -> list[str]:
    """음성 서버 주소 후보. 2026-10-10 부터 예전 주소(speech.platform.bing.com)는 지역에 따라 403 으로 거절하고,
    Edge 155 가 쓰는 새 주소(api.msedgeservices.com)는 예전 토큰을 그대로 받는다(edge-tts PR #491).
    새 주소 먼저, 안 되면 예전 주소로 다시 해 본다. 주소는 communicate 모듈 쪽 값을 바꿔야 적용된다."""
    import edge_tts.communicate as M
    import edge_tts.constants as C
    new = ("wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
           f"?Ocp-Apim-Subscription-Key={C.TRUSTED_CLIENT_TOKEN}")
    legacy = f"wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken={C.TRUSTED_CLIENT_TOKEN}"
    cur = getattr(M, "WSS_URL", legacy)
    return list(dict.fromkeys([new, cur, legacy]))


def _why(e: Exception) -> str:
    """사람이 읽을 실패 이유(상태 코드 포함). 예: 'api.msedgeservices.com 403'."""
    status = getattr(e, "status", None)
    host = "api.msedgeservices.com" if "msedgeservices" in str(e) else "speech.platform.bing.com" if "bing.com" in str(e) else ""
    return " ".join(x for x in [host, str(status) if status else type(e).__name__] if x)


def synthesize(lines: list[Line], out_dir: Path, voice: str = VOICE, base_rate: int = RATE, log=print) -> list[Line]:
    """문장별 wav(48kHz mono)를 만들고 길이를 채워 돌려준다. 앞뒤 완전 무음만 정리하고 끝음절 꼬리는 살린다."""
    _use_proxy_ca()
    import edge_tts
    import edge_tts.communicate as M
    hosts = _edge_hosts()

    out_dir.mkdir(parents=True, exist_ok=True)
    async def one(ln: Line):
        raw = out_dir / f"{ln.key}.raw.mp3"
        why = []
        for attempt in range(3):
            for host in list(hosts):
                M.WSS_URL = host             # 모듈 값이라 문장을 하나씩 만든다(새 주소는 한꺼번에 몰리면 429 로 거절하기도 함)
                try:
                    await edge_tts.Communicate(ln.text, voice, rate=f"{base_rate + ln.rate:+d}%",
                                               pitch=f"{ln.pitch:+d}Hz").save(str(raw))
                    hosts[:] = [host] + [h for h in hosts if h != host]   # 된 주소를 다음 문장부터 먼저
                    return raw
                except Exception as e:
                    why.append(_why(e))
            await asyncio.sleep(2 * (attempt + 1))
        raise RuntimeError(f"목소리 서버가 거절했어요({', '.join(dict.fromkeys(why))})")

    async def all_():
        return [await one(ln) for ln in lines]

    raws = asyncio.run(all_())
    for ln, raw in zip(lines, raws):
        wav = out_dir / f"{ln.key}.wav"
        # 앞뒤 무음을 자른 자리는 소리가 갑자기 시작·끝나서 '틱' 하고 튄다 → 앞 15ms·뒤 40ms 를 부드럽게
        trim = ("silenceremove=start_periods=1:start_threshold=-65dB:start_silence=0.05,afade=t=in:d=0.015,areverse,"
                "silenceremove=start_periods=1:start_threshold=-65dB:start_silence=0.12,afade=t=in:d=0.04,areverse")
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
    # 음량 맞추기: 한 번에 하는 loudnorm 은 소리를 순간순간 키웠다 줄였다 해서 문장 시작에 '지직'이 생긴다.
    # 먼저 섞은 뒤 재고(1차), 잰 값으로 전체를 한 번에 같은 비율로 맞춘다(2차).
    mixed = out.with_suffix(".mix.wav")
    subprocess.run([FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", last,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_f32le", str(mixed)], check=True)
    m = _measure(mixed)
    gain = -14.0 - float(m["input_i"])            # 전체를 같은 비율로 올리고, 넘치는 순간만 리미터로 누른다(-1.5 dBTP)
    ln = f"volume={gain:.2f}dB,alimiter=limit=0.84:attack=5:release=50:level=disabled"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(mixed), "-af", ln, "-ar", "48000", "-ac", "2",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    mixed.unlink(missing_ok=True)


def _measure(wav: Path) -> dict:
    """loudnorm 1차 측정값(JSON)."""
    import json
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(wav), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    return json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])

"""목소리 고르기 (DESIGN.md 7절): 기본 AI 목소리(edge-tts) · 목소리 없이 자막만 · 내 목소리로 녹음 · 유료 음성 API · 다른 언어 목소리.

장면 표의 브랜드 목소리(sc.brand.voice)에 아래 중 하나가 들어간다.
- 'ko-KR-HyunsuMultilingualNeural' 같은 edge-tts 이름 (기본, 무료, 인터넷 필요)
- '자막만'      : 소리 없이 자막으로만. 문장 길이는 읽는 속도로 계산(1편 현수 목소리 길이에서 맞춘 식)
- '내목소리'    : 화면에서 문장마다 녹음한 파일(작업 폴더 my_voice/<키>.webm|wav) → 잡음 정리·앞뒤 무음 정리·음색
- 'openai:<목소리>' : OpenAI 음성 API (키가 보관함에 있을 때만 목록에 나옴). 문장만 전송

어느 것이든 결과는 같다: 문장별 48kHz wav + 길이 → narration.json. 그 뒤 녹화·편집은 목소리 종류를 모른다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from ..ffmpeg_utils import FFMPEG

# (화면 이름, 목소리, 기본 빠르기, 언어) — 앞 셋은 4단계부터 있던 것(이름을 바꾸면 저장된 선택이 풀림)
EDGE = [
    ("현수 · 차분", "ko-KR-HyunsuMultilingualNeural", -8, "ko"),
    ("선희 · 밝게", "ko-KR-SunHiNeural", 0, "ko"),
    ("인준 · 또박또박", "ko-KR-InJoonNeural", -4, "ko"),
]
# 다른 언어 목소리(다국어 음성 트랙용). 현수 다국어 목소리는 여러 언어를 읽지만, 그 나라 목소리가 더 자연스럽다
LANG_VOICES = {
    "en": ("en-US-AndrewMultilingualNeural", -4), "ja": ("ja-JP-KeitaNeural", -4), "zh": ("zh-CN-YunxiNeural", -4),
    "vi": ("vi-VN-NamMinhNeural", -4), "es": ("es-ES-AlvaroNeural", -4), "fr": ("fr-FR-HenriNeural", -4),
    "de": ("de-DE-ConradNeural", -4), "id": ("id-ID-ArdiNeural", -4), "th": ("th-TH-NiwatNeural", -4),
}
SILENT, MINE = "자막만", "내목소리"
SILENT_NAME, MINE_NAME = "목소리 없이 자막만", "내 목소리로 녹음"
OPENAI_VOICES = [("OpenAI · 차분한 남성", "openai:onyx"), ("OpenAI · 밝은 여성", "openai:nova")]
OPENAI_KEY = "openai.com|api_key"           # 보관함 열쇠
OPENAI_MODEL = "gpt-4o-mini-tts"

# 소리를 정리하는 체인(목소리 공통): narration.VOICE_CHAIN 과 같음 + 내 목소리는 앞에 잡음 줄이기
TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,areverse,"
        "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.15,areverse")


def openai_key() -> str | None:
    from . import secrets as SEC
    return os.environ.get("OPENAI_API_KEY") or SEC.get(OPENAI_KEY)


def choices() -> list[dict]:
    """선택 단계에 보이는 목소리 목록. 유료 API 는 키가 있을 때만(없으면 '키 넣으면 추가' 안내만)."""
    out = [{"name": n, "voice": v, "rate": r, "kind": "ai"} for n, v, r, _ in EDGE]
    if openai_key():
        out += [{"name": n, "voice": v, "rate": 0, "kind": "paid"} for n, v in OPENAI_VOICES]
    out += [{"name": MINE_NAME, "voice": MINE, "rate": 0, "kind": "mine"},
            {"name": SILENT_NAME, "voice": SILENT, "rate": 0, "kind": "silent"}]
    return out


def find(name: str) -> dict | None:
    return next((c for c in choices() if c["name"] == name), None)


def read_seconds(text: str) -> float:
    """자막만일 때 문장이 화면에 머무는 시간. 1편 현수(-8%) 문장 길이에 맞춘 식: 글자 0.19초 + 쉼표·마침표 0.24초 + 0.26초.
    읽는 사람은 듣는 사람보다 조금 느리므로 10% 넉넉히, 최소 1.6초."""
    chars = len(re.sub(r"[\s,.!?·…]", "", text))
    pauses = text.count(",") + text.count(".")
    return round(max(1.6, (0.19 * chars + 0.24 * pauses + 0.26) * 1.1), 3)


def _dur(wav: Path) -> float:
    import wave
    with wave.open(str(wav), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _finish(src: Path, wav: Path, denoise: bool = False):
    from ..narration import VOICE_CHAIN
    af = ("afftdn=nf=-25," if denoise else "") + f"{TRIM},{VOICE_CHAIN}"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-af", af, "-ar", "48000", "-ac", "1", str(wav)], check=True)


def silent(lines, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ln in lines:
        wav = out_dir / f"{ln.key}.wav"
        d = read_seconds(ln.text)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{d:.3f}",
                        "-c:a", "pcm_s16le", str(wav)], check=True)
        ln.path, ln.duration = str(wav), d


def my_voice_dir(work: Path) -> Path:
    return work / "my_voice"


def my_voice_missing(lines, work: Path) -> list[str]:
    d = my_voice_dir(work)
    return [ln.key for ln in lines if not any((d / f"{ln.key}{e}").exists() for e in (".webm", ".wav", ".ogg", ".m4a"))]


def mine(lines, work: Path, out_dir: Path) -> None:
    missing = my_voice_missing(lines, work)
    if missing:
        raise ValueError(f"아직 녹음하지 않은 문장이 있어요: {', '.join(missing)}. 선택 단계의 '내 목소리로 녹음'에서 녹음해 주세요.")
    out_dir.mkdir(parents=True, exist_ok=True)
    d = my_voice_dir(work)
    for ln in lines:
        src = next(d / f"{ln.key}{e}" for e in (".webm", ".wav", ".ogg", ".m4a") if (d / f"{ln.key}{e}").exists())
        wav = out_dir / f"{ln.key}.wav"
        _finish(src, wav, denoise=True)
        ln.path, ln.duration = str(wav), _dur(wav)


def openai_tts(lines, out_dir: Path, voice: str, rate: int = 0, instructions: str = "") -> None:
    key = openai_key()
    if not key:
        raise ValueError("OpenAI 키가 없어요. ⚙ 설정에서 키를 넣으면 이 목소리를 쓸 수 있어요.")
    from ..narration import _use_proxy_ca
    _use_proxy_ca()
    import certifi
    import ssl
    ctx = ssl.create_default_context(cafile=certifi.where())
    out_dir.mkdir(parents=True, exist_ok=True)
    speed = round(1 + rate / 100, 2)
    for ln in lines:
        raw = out_dir / f"{ln.key}.raw.wav"
        body = {"model": OPENAI_MODEL, "voice": voice.split(":", 1)[1], "input": ln.text, "response_format": "wav",
                "speed": speed, "instructions": instructions or "따라 하기 사용법 영상의 차분하고 또박또박한 안내 목소리로 읽어 주세요."}
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                raw.write_bytes(r.read())
        except urllib.error.HTTPError as e:
            raise ValueError(f"OpenAI 음성 요청이 실패했어요({e.code}). 키와 사용 한도를 확인해 주세요.") from e
        wav = out_dir / f"{ln.key}.wav"
        _finish(raw, wav)
        ln.path, ln.duration = str(wav), _dur(wav)


def synthesize(lines, work: Path, out_dir: Path, voice: str, rate: int, log=print) -> None:
    """목소리 종류에 맞게 문장별 wav 를 만든다(ln.path, ln.duration 을 채움)."""
    from .. import narration as N
    if voice == SILENT:
        silent(lines, out_dir)
        log(f"[목소리] 자막만: {len(lines)}문장, 읽는 시간 {sum(l.duration for l in lines):.1f}초")
    elif voice == MINE:
        mine(lines, work, out_dir)
        log(f"[목소리] 내 목소리: {len(lines)}문장, 말 {sum(l.duration for l in lines):.1f}초")
    elif voice.startswith("openai:"):
        openai_tts(lines, out_dir, voice, rate)
        log(f"[목소리] OpenAI: {len(lines)}문장, 말 {sum(l.duration for l in lines):.1f}초")
    else:
        N.synthesize(lines, out_dir, voice=voice, base_rate=rate, log=log)


def fingerprint(voice: str, rate: int, work: Path) -> dict:
    """다시 만들지 판단할 재료: 내 목소리는 녹음 파일이 바뀌면 다시."""
    meta = {"voice": voice, "rate": rate}
    if voice == MINE and my_voice_dir(work).exists():
        meta["files"] = {f.name: f.stat().st_mtime for f in sorted(my_voice_dir(work).iterdir())}
    return meta

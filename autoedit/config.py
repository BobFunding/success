from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = PROJECT_DIR / ".env") -> None:
    """.env 파일의 KEY=VALUE 를 환경변수로 읽어온다.
    편집할 때마다 다시 읽고 .env 값을 우선한다 → 웹 화면을 켜 둔 채로 키를 넣거나 바꿔도 다음 편집부터 바로 적용."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:  # 빈 값(KEY=)은 무시해서 시스템에 설정된 키를 지우지 않는다
            os.environ[key.strip()] = value


@dataclass
class Settings:
    # ── 받아쓰기 ──
    whisper_model: str = "large-v3"
    language: str = "ko"         # "ko+en" = 언어마다 받아 적고 구간별로 더 잘 들린 쪽을 고름 (섞인 영상)
    vocabulary: list[str] = field(default_factory=list)  # 주제 용어 힌트 (예: 복리, 단리) → 받아쓰기 오류 감소
    transcript_correction: bool = True  # Claude가 용어·문맥을 보고 잘못 받아 적은 단어를 교정 (단어 수·시간은 유지)

    # ── 1차 컷 편집 ──
    cut_enabled: bool = True
    pad: float = 0.12            # 말 앞뒤로 남겨둘 여유(초)
    max_pause: float = 0.45    # 이보다 긴 무음은 잘라서 pad*2 정도만 남김
    min_segment: float = 0.20    # 이보다 짧게 남는 조각은 버림
    llm_filler_review: bool = True  # 애매한 필러("그", "아", "이제" 등)는 Claude가 문맥 보고 판단

    # ── 설명 일러스트 ──
    illustrations_enabled: bool = True
    seconds_per_illustration: float = 40.0  # 평균 몇 초에 한 장 정도 넣을지 (상한)
    min_illustration_sec: float = 3.0
    max_illustration_sec: float = 6.0
    illustration_review: bool = True   # (claude-svg 엔진) 렌더링 결과를 Claude가 보고 깨진 그림이면 고침
    illustration_engine: str = "gpt"   # gpt = GPT 이미지 병렬 생성 / claude-svg = Claude가 SVG로 직접 그림
    # 일러스트 배치: full = 전체 설명 화면 / side = 화자 옆 카드 / sticker = 말하는 사람 근처에 잠깐 붙는 작은 아이콘
    gpt_image_model: str = "gpt-image-2"
    gpt_image_quality: str = "medium"  # low / medium / high — 높을수록 느리고 비쌈
    image_workers: int = 6             # 동시에 생성할 이미지 수

    # ── 전환 효과 ──
    fade_in: float = 0.40              # 일러스트 나타나는 시간(초)
    fade_out: float = 0.35             # 사라지는 시간(초)
    card_slide: int = 60               # 옆 카드가 미끄러져 들어오는 거리(px, 720p 기준)
    full_zoom: float = 0.04            # 전체 화면 일러스트가 천천히 확대되는 정도 (켄 번즈)
    audio_crossfade: float = 0.015     # 컷 경계 '틱' 소리 방지용 오디오 페이드(초)

    # ── 개인정보 ──
    privacy_enabled: bool = True
    ocr_interval: float = 0.5          # 화면 글자 검사 간격(초)
    beep_spoken_pii: bool = True       # 말로 나온 개인정보는 삐- 처리
    privacy_allowlist: list[str] = field(default_factory=list)  # 가리지 않을 단어(본인 이름, 채널명 등)
    mosaic_block: int = 14             # 모자이크 블록 크기(px)

    # ── 자막 ──
    burn_subtitles: bool = True        # 최종본 화면에 자막을 입힘 (subtitles.srt 는 항상 따로 만듦)
    subtitle_font: str = "Malgun Gothic"
    subtitle_size: float = 0.055       # 글자 높이 = 영상 높이 × 이 값
    subtitle_translate: str = ""       # "ko" 면 외국어 문장을 한국어로 번역해 크게 띄우고 원문은 아래 작게

    # ── 출력 / 모델 ──
    model: str = "claude-opus-5-5"
    quality_cq: int = 19               # 낮을수록 고화질 (NVENC cq / x264 crf)
    x264_preset: str = "medium"        # GPU 없을 때 x264 속도 (4K 를 CPU 로 뽑을 땐 veryfast 권장)

    def to_dict(self) -> dict:
        return asdict(self)

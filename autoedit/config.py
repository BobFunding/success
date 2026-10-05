from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = PROJECT_DIR / ".env") -> None:
    """.env 파일의 KEY=VALUE 를 환경변수로 읽어온다 (이미 설정된 값은 유지)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    # ── 받아쓰기 ──
    whisper_model: str = "large-v3"
    language: str = "ko"
    vocabulary: list[str] = field(default_factory=list)  # 주제 용어 힌트 (예: 복리, 단리) → 받아쓰기 오류 감소

    # ── 1차 컷 편집 ──
    cut_enabled: bool = True
    pad: float = 0.12            # 말 앞뒤로 남겨둘 여유(초)
    max_pause: float = 0.45      # 이보다 긴 무음은 잘라서 pad*2 정도만 남김
    min_segment: float = 0.20    # 이보다 짧게 남는 조각은 버림
    llm_filler_review: bool = True  # 애매한 필러("그", "아", "이제" 등)는 Claude가 문맥 보고 판단

    # ── 설명 일러스트 ──
    illustrations_enabled: bool = True
    seconds_per_illustration: float = 40.0  # 평균 몇 초에 한 장 정도 넣을지 (상한)
    min_illustration_sec: float = 3.0
    max_illustration_sec: float = 6.0
    illustration_review: bool = True   # (claude-svg 엔진) 렌더링 결과를 Claude가 보고 깨진 그림이면 고침
    illustration_engine: str = "gpt"   # gpt = GPT 이미지 병렬 생성 / claude-svg = Claude가 SVG로 직접 그림
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

    # ── 출력 / 모델 ──
    model: str = "claude-opus-5-5"
    quality_cq: int = 19               # 낮을수록 고화질 (NVENC cq / x264 crf)

    def to_dict(self) -> dict:
        return asdict(self)

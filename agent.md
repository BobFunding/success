# Agent 가이드 — 유튜브 자동 편집기

이 저장소에서 작업하는 AI 에이전트와 개발자를 위한 안내입니다. 사용자용 설명은 `README.md` 를 보세요.

- **작업을 시작하기 전에 `memory.md` 를 읽으세요.** 현재 상태, 지난 결정, 남은 과제가 있습니다. 작업을 마치면 갱신합니다.
- `feedback-ocr-speed.md`: OCR 속도 측정치와 개선 방안입니다.

## 개요

업로드한 영상을 아래 순서로 처리하는 Python 파이프라인입니다.

1. **받아쓰기**: faster-whisper(large-v3)로 단어 단위 타임스탬프를 얻습니다.
2. **1차 컷**: 무음과 필러워드("어", "음")를 잘라 `1_cut.mp4` 를 만듭니다.
3. **개인정보**: 화면은 EasyOCR + 정규식 + Claude 판단으로 찾아 모자이크하고, 음성은 대본에서 찾아 삐- 처리합니다.
4. **설명 일러스트**: Claude가 삽입 지점을 기획하고, 플랫 벡터 + 핸드드로잉 카툰 스타일 SVG를 그린 뒤 resvg로 PNG를 만듭니다.
5. **최종 합성**: ffmpeg 필터 그래프 하나로 모자이크, 삐-, 일러스트를 합쳐 `2_final.mp4` 를 만듭니다.

## 구조

```
app.py               Gradio 웹 UI (실행.bat 이 이걸 띄움)
run.py               CLI. --rerender <작업폴더> 로 edit_plan.json 기준 재렌더링
autoedit/
  config.py          Settings 데이터클래스 (모든 조절값), .env 로더
  pipeline.py        전체 순서 조율, report.md / subtitles.srt / edit_plan.json 작성
  transcribe.py      Whisper 받아쓰기, 문장 묶기
  cutter.py          필러 판정, 무음 감지, 남길 구간 계산, TimeMap(원본↔컷 시간 변환), 컷 렌더링
  privacy.py         OCR 기반 화면 개인정보, 대본 기반 음성 개인정보
  illustrate.py      일러스트 기획 / SVG 생성 / 렌더 검수
  render.py          최종 ffmpeg 합성
  llm.py             Claude 호출 래퍼 (구조화 출력, 서버측 fallback, 키 없을 때 비활성화)
  ffmpeg_utils.py    ffmpeg 경로 탐색, probe, NVENC 감지, 필터 스크립트 인자
```

## 핵심 설계 원칙

- **시간 기준이 두 가지입니다.** 받아쓰기는 원본 시간, 개인정보·일러스트·최종 합성은 컷 편집본 시간입니다. 변환은 반드시 `cutter.TimeMap` 을 거칩니다.
- **`edit_plan.json` 이 최종 합성의 유일한 입력입니다.** 사람이 검수하고 고칠 수 있도록 AI 판단 결과는 모두 여기에 저장합니다. 최종 렌더링 로직은 이 파일만 보고 동작해야 합니다.
- **Claude가 없어도 돌아가야 합니다.** API 키가 없으면 `LLM.available=False` 가 되고, 각 단계는 규칙 기반으로 대체하거나 건너뜁니다. 새 AI 기능도 같은 방식으로 실패를 처리하세요(`LLMUnavailable`).
- **개인정보는 과하게 가리는 쪽이 안전합니다.** 애매하면 가리고, 모자이크 구간은 앞뒤로 여유를 둡니다. 리포트에도 원문을 남기지 않습니다(`pipeline._mask`).
- **컷은 보수적으로 합니다.** 이해를 해치지 않는 것이 우선이며, 의미가 있을 수 있는 단어는 남깁니다.
- **자막은 개인정보 감지 뒤에 씁니다.** 삐- 처리한 말이 `subtitles.srt` 에 남으면 안 됩니다(`pipeline.subtitle_cues`).
- **옆 카드는 화면 글자를 피합니다.** OCR 글자 위치(`ocr_text_boxes.json`)를 보고 자리와 크기를 정합니다(`illustrate.place_cards`).

## 환경

- Windows, Python 3.12, 가상환경은 `.venv`. 실행은 `.venv\Scripts\python.exe`.
- ffmpeg 9.x (winget `Gyan.FFmpeg`). ffmpeg 7 이상에서는 `-filter_complex_script` 대신 `-/filter_complex <파일>` 을 씁니다(`ffmpeg_utils.filter_script_args`).
- GPU: torch cu124. faster-whisper가 cuBLAS/cuDNN DLL을 찾도록 torch/lib 를 DLL 경로에 추가합니다(`transcribe._add_cuda_dll_dirs`).
- 비밀 키는 `.env` 의 `ANTHROPIC_API_KEY` 에 둡니다. 절대 커밋하지 않습니다.

## 알려진 함정

- faster-whisper에 파일 경로를 넘기면 최신 PyAV와 충돌합니다(`metadata_errors` 오류). wav를 numpy 배열로 읽어서 넘기세요.
- Whisper는 필러를 생략하는 경향이 있어 `FILLER_PROMPT` 로 받아적게 유도합니다. `vad_filter` 를 켜면 필러가 사라집니다.
- OCR 재사용 판정은 평균 차이가 아니라 **바뀐 픽셀 비율**로 해야 작은 알림 글자도 잡힙니다.
- 모자이크 블록은 고정 크기면 큰 글자가 읽힙니다. 글자 높이 기준 세로 3칸 이하로 뭉갭니다.
- Whisper의 `hotwords` 나 `initial_prompt` 로는 발음이 바뀌는 단어("단리"→[달리])를 바로잡지 못합니다.
- Windows 음성합성(SAPI)으로 테스트 음성을 만들 때는 PromptBuilder에 `ko-KR` 문화권을 지정해야 한글을 읽습니다.

## 검증 방법

테스트 프레임워크는 아직 없습니다. 변경 후에는 짧은 테스트 영상으로 끝까지 실행하고, 결과물을 직접 확인하세요.

```bash
.venv\Scripts\python.exe run.py 테스트영상.mp4
.venv\Scripts\python.exe run.py --rerender output\<작업폴더>
```

- `report.md` 에서 컷, 모자이크, 삐- 목록 확인
- `ffmpeg -ss <초> -i 2_final.mp4 -frames:v 1 frame.png` 로 프레임을 뽑아 모자이크와 일러스트를 눈으로 확인
- Claude 관련 코드는 `.env` 키가 있어야 실제 검증이 가능합니다

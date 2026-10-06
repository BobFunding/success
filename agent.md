# Agent 가이드 — 유튜브 자동 편집기

이 저장소에서 작업하는 AI 에이전트와 개발자를 위한 안내입니다. 사용자용 설명은 `README.md` 를 보세요.

- **작업을 시작하기 전에 `memory.md` 를 읽으세요.** 현재 상태, 지난 결정, 남은 과제가 있습니다. 작업을 마치면 갱신합니다.
- `feedback-ocr-speed.md`: OCR 속도 측정치와 개선 방안입니다.

## 개요

업로드한 영상을 아래 순서로 처리하는 Python 파이프라인입니다.

1. **받아쓰기**: faster-whisper(large-v3)로 단어 단위 타임스탬프를 얻고, Claude가 주제 용어와 문맥을 보고 잘못 받아 적은 단어를 교정합니다(단어 수와 시간은 유지).
2. **1차 컷**: 무음과 필러워드("어", "음")를 잘라 `1_cut.mp4` 를 만듭니다.
3. **개인정보**: 화면은 EasyOCR + 정규식 + Claude 판단으로 찾아 모자이크하고, 음성은 대본에서 찾아 삐- 처리합니다.
4. **설명 일러스트**: Claude가 삽입 지점을 기획하고, 플랫 벡터 + 핸드드로잉 카툰 스타일 SVG를 그린 뒤 resvg로 PNG를 만듭니다.
5. **최종 합성**: ffmpeg 필터 그래프 하나로 모자이크, 삐-, 일러스트·스티커, 자막(번역 자막 포함)을 합쳐 `2_final.mp4` 를 만듭니다.

## 구조

```
app.py               Gradio 웹 UI (web.bat 이 이걸 띄움)
run.py               CLI. --rerender <작업폴더> 로 edit_plan.json 기준 재렌더링
autoedit/
  config.py          Settings 데이터클래스 (모든 조절값), .env 로더
  pipeline.py        전체 순서 조율, report.md / subtitles.srt / edit_plan.json 작성
  transcribe.py      Whisper 받아쓰기, 문장 묶기
  correct.py         Claude 받아쓰기 교정 (단어 하나 → 단어 하나만, 숫자·필러는 손대지 않음)
  cutter.py          필러 판정, 무음 감지, 남길 구간 계산, TimeMap(원본↔컷 시간 변환), 컷 렌더링
  privacy.py         OCR 기반 화면 개인정보, 대본 기반 음성 개인정보
  illustrate.py      일러스트 기획 / (claude-svg 엔진) SVG 생성·렌더 검수 / 카드 배치
  imagegen.py        (gpt 엔진, 기본값) GPT 이미지 병렬 생성 → 손그림 카드/설명 화면으로 합성, 라벨은 직접 그림
  translate.py       번역 자막 (외국어 문장 → 한국어, translations.json)
  render.py          최종 ffmpeg 합성 (모자이크·삐-·일러스트·스티커·ASS 자막)
  screenfx.py        화면 녹화 편집 (Screen Studio 스타일: 배경 프레임·자동 줌·클릭 효과·대기 구간 빨리 감기).
                     pipeline 과 완전히 별개 — 다른 모듈을 고치거나 부르지 않음
  llm.py             Claude 호출 래퍼 (구조화 출력, 서버측 fallback, 키 없을 때 비활성화)
  ffmpeg_utils.py    ffmpeg 경로 탐색, probe, NVENC 감지, 필터 스크립트 인자
tests/               pytest 단위 테스트 (가짜 LLM 사용, Whisper·GPU·API 키 없이 실행)
```

## 핵심 설계 원칙

- **시간 기준이 두 가지입니다.** 받아쓰기는 원본 시간, 개인정보·일러스트·최종 합성은 컷 편집본 시간입니다. 변환은 반드시 `cutter.TimeMap` 을 거칩니다.
- **`edit_plan.json` 이 최종 합성의 유일한 입력입니다.** 사람이 검수하고 고칠 수 있도록 AI 판단 결과는 모두 여기에 저장합니다. 최종 렌더링 로직은 이 파일만 보고 동작해야 합니다.
- **Claude가 없어도 돌아가야 합니다.** API 키가 없으면 `LLM.available=False` 가 되고, 각 단계는 규칙 기반으로 대체하거나 건너뜁니다. 새 AI 기능도 같은 방식으로 실패를 처리하세요(`LLMUnavailable`).
- **개인정보는 과하게 가리는 쪽이 안전합니다.** 애매하면 가리고, 모자이크 구간은 앞뒤로 여유를 둡니다. 리포트에도 원문을 남기지 않습니다(`pipeline._mask`).
- **컷은 보수적으로 합니다.** 이해를 해치지 않는 것이 우선이며, 의미가 있을 수 있는 단어는 남깁니다.
- **자막은 개인정보 감지 뒤에 씁니다.** 삐- 처리한 말이 `subtitles.srt` 에 남으면 안 됩니다(`pipeline.subtitle_cues`).
- **컷 경계는 프레임에 맞춥니다**(`cutter.snap_to_frames`, select 는 반 프레임 당겨 비교). 안 그러면 컷이 많을 때 입 모양과 소리가 밀립니다. 오디오는 구간마다 짧게 페이드한 뒤 이어붙입니다.
- **AI 이미지에 글자를 맡기지 않습니다.** GPT 이미지에는 글자를 넣지 말라고 지시하고, 라벨은 `imagegen.compose` 에서 직접 그립니다(한글이 깨지는 것을 막기 위함).
- **자막과 번역은 가린 대본으로 만듭니다**(`pipeline.masked_words`). 삐- 처리한 말이 번역문으로 새면 안 됩니다.
- **일러스트 배치는 세 가지입니다**: `full`(전체 설명 화면), `side`(옆 카드), `sticker`(말하는 사람 근처의 작은 아이콘, x·y·size 지정).
- **옆 카드는 화면 글자를 피합니다.** OCR 글자 위치(`ocr_text_boxes.json`)를 보고 자리와 크기를 정합니다(`illustrate.place_cards`).

## 환경

- Windows, Python 3.12, 가상환경은 `.venv`. 실행은 `.venv\Scripts\python.exe`.
- ffmpeg 9.x (winget `Gyan.FFmpeg`). ffmpeg 7 이상에서는 `-filter_complex_script` 대신 `-/filter_complex <파일>` 을 씁니다(`ffmpeg_utils.filter_script_args`).
- GPU: torch cu124. faster-whisper가 cuBLAS/cuDNN DLL을 찾도록 torch/lib 를 DLL 경로에 추가합니다(`transcribe._add_cuda_dll_dirs`).
- 비밀 키는 `.env` 의 `ANTHROPIC_API_KEY` 에 둡니다. 절대 커밋하지 않습니다.

## 알려진 함정

- 언어가 섞인 영상(한국어+영어 인터뷰)에서 언어를 `ko` 로 고정하면 영어 구간을 통째로 건너뛰고, `multilingual=True` 는 영어를 한국어로 번역해 지어냅니다. `language="ko+en"` 으로 언어마다 받아 적고 구간별로 avg_logprob 가 높은 쪽을 고릅니다(`transcribe.merge_language_passes`).
- 화면 녹화에서 커서와 글자 입력은 크기로 구분할 수 없습니다(글자가 커서보다 작음). 속도로도 안 됩니다(느린 커서). `screenfx.analyze` 는 '이번 프레임 차이와 다음 프레임 차이가 겹치는 작은 영역 = 커서'로 보고 지웁니다.
- 카메라 스프링은 목표가 화면 밖이면 속도가 쌓였다가 풀릴 때 튑니다. 목표를 화면 안으로 당기고, 막힌 방향 속도는 버립니다(`screenfx.camera_path`).
- 손으로 든 카메라는 매 프레임 화면이 조금씩 흔들려서 OCR 재사용 판정이 거의 안 걸립니다(82초 4K 영상에 OCR 81회, 552초, CPU).
- GPU 없이 4K 60fps 를 x264 `medium` 으로 뽑으면 매우 느립니다. `x264_preset="veryfast"` 면 82초 영상에 컷 228초, 최종 180초(4코어).
- faster-whisper에 파일 경로를 넘기면 최신 PyAV와 충돌합니다(`metadata_errors` 오류). wav를 numpy 배열로 읽어서 넘기세요.
- 필러 규칙(`cutter.STRONG_FILLER`)은 한국어("어", "음")와 영어("um", "uh", "hmm")를 함께 봅니다.
- Whisper는 필러를 생략하는 경향이 있어 `FILLER_PROMPT` 로 받아적게 유도합니다. `vad_filter` 를 켜면 필러가 사라집니다.
- OCR 재사용 판정은 평균 차이가 아니라 **바뀐 픽셀 비율**로 해야 작은 알림 글자도 잡힙니다.
- 모자이크 블록은 고정 크기면 큰 글자가 읽힙니다. 글자 높이 기준 세로 3칸 이하로 뭉갭니다.
- Whisper의 `hotwords` 나 `initial_prompt` 로는 발음이 바뀌는 단어("단리"→[달리])를 바로잡지 못합니다. 그래서 `correct.py` 가 받아쓰기 뒤에 교정합니다. 교정은 단어 수와 타임스탬프를 바꾸면 안 됩니다(컷·삐-·자막이 모두 단어 시간 기준).
- Windows 음성합성(SAPI)으로 테스트 음성을 만들 때는 PromptBuilder에 `ko-KR` 문화권을 지정해야 한글을 읽습니다.

## 검증 방법

순수 로직(필러 판정, 남길 구간 계산, TimeMap, 자막 분할, 개인정보 정규식, 카드 배치, 받아쓰기 교정)은 pytest 단위 테스트가 있습니다. Claude 호출은 `tests/conftest.py` 의 `FakeLLM` 으로 대신하므로 API 키 없이 돌아갑니다.

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

영상 처리를 바꿨다면 단위 테스트와 별개로 짧은 테스트 영상으로 끝까지 실행하고, 결과물을 직접 확인하세요.

```bash
.venv\Scripts\python.exe run.py 테스트영상.mp4
.venv\Scripts\python.exe run.py --rerender output\<작업폴더>
```

- `report.md` 에서 컷, 모자이크, 삐- 목록 확인
- `ffmpeg -ss <초> -i 2_final.mp4 -frames:v 1 frame.png` 로 프레임을 뽑아 모자이크와 일러스트를 눈으로 확인
- Claude 관련 코드는 `.env` 키가 있어야 실제 검증이 가능합니다

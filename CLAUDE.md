# CLAUDE.md

프로젝트 구조, 설계 원칙, 알려진 함정은 agent.md 에 있습니다.

@agent.md

## Claude Code 작업 규칙

- 사용자와는 **한국어**로 대화하고, 코드 주석과 로그 메시지도 한국어로 씁니다.
- 명령은 `.venv\Scripts\python.exe` 로 실행합니다. 시스템 Python에는 패키지가 없습니다.
- `.env`, `output/`, 영상 파일은 커밋하지 않습니다. 사용자 영상에는 개인정보가 있을 수 있습니다.
- Claude API 코드를 고칠 때는 `autoedit/llm.py` 래퍼를 거칩니다. 기본 모델은 `claude-opus-5-5` 이고, 구조화 출력은 pydantic 모델 + `output_format` 을 씁니다.
- 영상 처리 변경은 실제로 돌려서 프레임을 뽑아 확인한 뒤에 완료라고 보고합니다.

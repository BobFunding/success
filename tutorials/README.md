# 태권월드 튜토리얼 제작 스크립트

편마다 폴더 하나. 순서: 나레이션 생성(`lines.py` → `autoedit.narration.synthesize`, narration.json)
→ `record_epN.py dry`(리허설) → `record_epN.py rec`(Xvfb 2880x1620 + x11grab 무손실, 1.5배 배율)
→ 동기 표시(검은 화면 0.3초) 프레임을 찾아 sync.json → `build_epN.py`(인트로·본편·아웃트로·자막·나레이션 → 1440p60 / 1080p30).

- 녹화 창은 `launch_persistent_context` 의 기본 창 + `--kiosk` + `--window-size=1920,1080`(CSS 기준) + `--force-device-scale-factor=1.5`.
  새 컨텍스트 창을 쓰면 전체 화면이 안 되고, 창 크기를 화면 픽셀로 주면 페이지가 작게 그려진다.
- 가입 양식에서는 xhr/fetch 를 모두 막아 문자 발송·계정 생성이 실제로 일어나지 않게 한다.
- 개인정보 칸은 CSS 로 글자를 투명 + 흐린 그림자로 바꿔 녹화 중에도 값이 보이지 않게 한다.
- 스크립트 안의 경로는 작업 폴더(스크래치) 기준이다. 녹화본·음성 등 산출물은 커밋하지 않는다.

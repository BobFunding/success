# 3단계 검사: 다른 사이트로 시연 → 영상까지

연습용 사이트(`tutorials/sample_site`, 푸른숲 도서관 회원가입)에서 사람처럼 한 번 해 보이고(실수 메뉴 누르고 뒤로 가기, 빈 곳 누르기,
오타 고치기, 체크 켰다 껐다 켜기), 그 기록으로 장면 표를 만든 뒤 영상까지 만들었습니다.

```bash
python -m http.server 8765 -d tutorials/sample_site     # 연습용 사이트
python tutorials/demo_check/run_demo.py                  # 시연 흉내 → scenario.yaml
TUTORIAL_SECRET='book1234!' python tutorial.py make tutorials/demo_check/scenario.yaml --fast
```

결과(2026-10-10): 동작 60개 → 장면 8개, 3단계, 47.7초 영상. 실수·머뭇거림은 모두 버려졌고, 이메일 + 중복 확인은 한 장면으로,
비밀번호는 장면 표에 남지 않음(`@보관함`), 이름·이메일·비밀번호 칸은 자동으로 흐림. 프레임: `demo_frames.png`.
사람이 직접 할 때는 `python tutorial.py demo <주소> --topic "주제"` (브라우저에서 한 번 한 뒤 검은 창에서 Enter).

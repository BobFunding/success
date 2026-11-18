#!/usr/bin/env bash
# 튜토리얼 메이커 실행 (Mac: 더블클릭). 브라우저에 화면이 뜹니다. 이 창은 켜 두세요.
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "아직 설치가 안 되어 있습니다. 먼저 bash setup.sh 를 실행해 주세요."; exit 1; }
exec .venv/bin/python tutorial.py ui

#!/usr/bin/env bash
# 튜토리얼 메이커 설치 (Mac·Linux). 처음 한 번만 실행합니다: 터미널에서 bash setup.sh
set -e
cd "$(dirname "$0")"
echo "튜토리얼 메이커 설치를 시작합니다 (Python, FFmpeg, 브라우저). 10분쯤 걸릴 수 있어요."
if [ "$(uname)" = "Darwin" ]; then
  command -v brew >/dev/null || { echo "Homebrew 가 필요합니다: https://brew.sh 의 안내대로 설치한 뒤 다시 실행해 주세요."; exit 1; }
  command -v python3.12 >/dev/null || brew install python@3.12
  command -v ffmpeg >/dev/null || brew install ffmpeg
  PY=$(command -v python3.12 || command -v python3)
else
  need=""
  command -v python3 >/dev/null || need="$need python3 python3-venv"
  command -v ffmpeg >/dev/null || need="$need ffmpeg"
  command -v Xvfb >/dev/null || need="$need xvfb"          # 녹화용 가상 화면 (없으면 한 장씩 찍기로 녹화)
  [ -n "$need" ] && { echo "설치:$need"; sudo apt-get update && sudo apt-get install -y $need; }
  PY=$(command -v python3)
fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
# 품질 검사(글자 인식)용 torch: CPU 판 (Mac 은 기본 판)
if [ "$(uname)" = "Darwin" ]; then .venv/bin/python -m pip install torch torchvision; \
else .venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu; fi
.venv/bin/python -m pip install -r requirements-tutorial.txt
.venv/bin/python -m playwright install chromium
[ "$(uname)" = "Darwin" ] || .venv/bin/python -m playwright install-deps chromium || true
chmod +x tutorial.sh 튜토리얼.command 2>/dev/null || true
echo "설치 완료! Mac 은 튜토리얼.command, Linux 는 tutorial.sh 를 실행하세요."

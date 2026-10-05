@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 자동 새로고침 모드: 코드(app.py, autoedit\)를 고치면 재실행 없이 바로 반영된다.
rem .env(API 키)는 편집을 시작할 때마다 다시 읽는다.
rem 주의: 영상 처리 중에 코드를 저장하면 진행 중인 작업이 끊길 수 있다.
start "" /b powershell -NoProfile -Command "Start-Sleep 6; Start-Process http://127.0.0.1:7860"
".venv\Scripts\gradio.exe" app.py --watch-dirs autoedit
pause

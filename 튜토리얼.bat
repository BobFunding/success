@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 튜토리얼 메이커
set PYTHONIOENCODING=utf-8
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" goto :nosetup
rem 튜토리얼 메이커 부품이 없으면 한 번만 설치 (setup.bat 을 예전에 돌린 PC)
"%VPY%" -c "import playwright, edge_tts, yaml, resvg_py" > nul 2>&1
if errorlevel 1 goto :install
:run
echo 튜토리얼 메이커를 여는 중입니다. 브라우저에 화면이 뜹니다.
echo 이 검은 창은 켜 두세요. 끄면 프로그램도 꺼집니다.
"%VPY%" tutorial.py ui
pause
exit /b 0

:install
echo 튜토리얼 메이커 부품을 처음 한 번 설치합니다. 몇 분 걸려요...
"%VPY%" -m pip install -r requirements-tutorial.txt
if errorlevel 1 goto :fail
"%VPY%" -m playwright install chromium
if errorlevel 1 goto :fail
goto :run

:nosetup
echo 아직 설치가 안 되어 있습니다. 같은 폴더의 setup.bat 을 먼저 더블클릭해 주세요.
pause
exit /b 1

:fail
echo 설치를 마치지 못했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
pause
exit /b 1

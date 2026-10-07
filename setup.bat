@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title 유튜브 자동 편집기 - 처음 설치

echo ============================================================
echo   유튜브 자동 편집기 - 처음 한 번만 실행하는 설치 프로그램
echo   (Python 3.12, FFmpeg, 필요한 패키지를 자동으로 설치합니다)
echo   인터넷 속도에 따라 10~30분 걸릴 수 있습니다.
echo ============================================================
echo.

rem ── 0. winget 확인 (Windows 10/11 기본 포함, 없으면 Microsoft Store 의 "앱 설치 관리자") ──
where winget > nul 2>&1
if errorlevel 1 (
    echo [오류] winget 이 없습니다. Microsoft Store 에서 "앱 설치 관리자"를 설치한 뒤 다시 실행해 주세요.
    goto :fail
)

rem ── 1. Python 3.12 ──
set "PY="
py -3.12 --version > nul 2>&1 && set "PY=py -3.12"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
    echo [1/5] Python 3.12 설치 중...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    rem 설치 직후에는 PATH 가 갱신되지 않으므로 설치 경로를 직접 쓴다
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        py -3.12 --version > nul 2>&1 && set "PY=py -3.12"
    )
)
if not defined PY (
    echo [오류] Python 3.12 를 찾을 수 없습니다. 이 창을 닫고 새로 연 뒤 setup.bat 을 다시 실행해 주세요.
    goto :fail
)
echo [1/5] Python 준비됨: !PY!

rem ── 2. FFmpeg ──
where ffmpeg > nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
        echo [2/5] FFmpeg 준비됨
    ) else (
        echo [2/5] FFmpeg 설치 중...
        winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    )
) else (
    echo [2/5] FFmpeg 준비됨
)

rem ── 3. 가상환경(.venv) ──
if not exist ".venv\Scripts\python.exe" (
    echo [3/5] 가상환경 만드는 중...
    !PY! -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경을 만들지 못했습니다.
        goto :fail
    )
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip > nul

rem ── 4. PyTorch: NVIDIA 그래픽카드가 있으면 GPU 버전, 없으면 CPU 버전 ──
"%VPY%" -c "import torch" > nul 2>&1
if errorlevel 1 (
    where nvidia-smi > nul 2>&1
    if errorlevel 1 (
        echo [4/5] PyTorch^(CPU^) 설치 중... 그래픽카드가 없어 받아쓰기가 느릴 수 있습니다.
        "%VPY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    ) else (
        echo [4/5] PyTorch^(GPU^) 설치 중... 약 3GB
        "%VPY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    )
    if errorlevel 1 (
        echo [오류] PyTorch 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
        goto :fail
    )
) else (
    echo [4/5] PyTorch 준비됨
)

rem ── 5. 나머지 패키지 ──
echo [5/5] 필요한 패키지 설치 중...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [오류] 패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
    goto :fail
)

rem ── API 키 파일 ──
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo.
    echo .env 파일을 만들었습니다. AI 기능을 쓰려면 메모장으로 열어 API 키를 넣어 주세요.
    echo ^(키가 없어도 무음·필러 컷, 개인정보 모자이크, 자막은 동작합니다^)
)

echo.
echo ============================================================
echo   설치 완료! 이제 web.bat 을 더블클릭해서 실행하세요.
echo   첫 실행 때 음성인식 모델(약 3GB)을 한 번 더 내려받습니다.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo 설치를 마치지 못했습니다. 위 메시지를 확인해 주세요.
pause
exit /b 1

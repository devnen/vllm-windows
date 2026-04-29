@echo off
REM ===================================================================
REM  vllm-windows launcher — portable Windows TUI
REM
REM  This .bat is the only thing you need to run. It uses the embeddable
REM  Python that ships next to it (..\python\) — no pip install, no
REM  conda, no admin, no internet required.
REM ===================================================================

setlocal EnableDelayedExpansion
title vLLM Launcher

cd /d "%~dp0"
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"
set "REPO_ROOT=%APP_ROOT%\.."

REM Prefer a sibling 'python\' (portable embed). Fall back to a 'venv\python.exe'
REM when running from a developer checkout.
if exist "%REPO_ROOT%\python\python.exe" (
    set "PYTHON=%REPO_ROOT%\python\python.exe"
    set "PYTHONHOME=%REPO_ROOT%\python"
) else if exist "%APP_ROOT%\python\python.exe" (
    set "PYTHON=%APP_ROOT%\python\python.exe"
    set "PYTHONHOME=%APP_ROOT%\python"
) else if exist "%REPO_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON=%REPO_ROOT%\venv\Scripts\python.exe"
) else (
    echo [start.bat] could not find a Python interpreter. Expected:
    echo    %REPO_ROOT%\python\python.exe   (portable release zip)
    echo    %REPO_ROOT%\venv\Scripts\python.exe   (developer checkout)
    pause
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PYTHONPATH=%APP_ROOT%"

REM Open inside Windows Terminal if available — the launcher's TUI looks
REM much better there than in legacy cmd. Skip if already inside WT.
if not defined WT_SESSION if not defined VLLM_NO_WT (
    set "WT_EXE="
    if exist "C:\Program Files\WindowsTerminal\wt.exe" set "WT_EXE=C:\Program Files\WindowsTerminal\wt.exe"
    if not defined WT_EXE if exist "C:\Program Files\WindowsTerminal\WindowsTerminal.exe" set "WT_EXE=C:\Program Files\WindowsTerminal\WindowsTerminal.exe"
    if defined WT_EXE (
        "!WT_EXE!" -w vllm-launcher new-tab -d "%APP_ROOT%" --title "vLLM Launcher" cmd /c """%~f0""" %*
        exit /b 0
    )
)

"%PYTHON%" -m app %*
exit /b %ERRORLEVEL%

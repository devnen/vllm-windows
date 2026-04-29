@echo off
REM =====================================================================
REM  Preserve 72 tok/s baseline: Qwen3.6-27B Lorbus AutoRound INT4
REM  TP=1 PP=1 MTP n=3 fp8_e4m3 TRITON_ATTN ctx=32k GPU1 only
REM  Do not edit start_72tps.py's knobs above without updating this file.
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

REM Relaunch inside Windows Terminal if available so vLLM output is visible.
if not defined WT_SESSION (
    set "WT_EXE=C:\Program Files\WindowsTerminal\wt.exe"
    if exist "!WT_EXE!" (
        "!WT_EXE!" -d "%~dp0." cmd /k """%~f0"""
        exit /b 0
    )
)

if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"

"%VLLM_WINDOWS_VENV%\Scripts\python.exe" -u "%~dp0start_72tps.py"
endlocal

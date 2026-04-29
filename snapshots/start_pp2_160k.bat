@echo off
REM =====================================================================
REM  PP=2 + ngram spec-decode variant.
REM  Uses GPU0 + GPU1 to enable ctx=96k. Trades MTP (and some tok/s) for
REM  a much bigger context window. Listens on :5002 — can run alongside
REM  the 72 tok/s baseline on :5001.
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
REM Both GPUs exposed; start_pp2_ngram.py sets this again to be explicit.
set CUDA_VISIBLE_DEVICES=0,1

REM Relaunch inside Windows Terminal if available so vLLM output is visible.
if not defined WT_SESSION (
    set "WT_EXE=C:\Program Files\WindowsTerminal\wt.exe"
    if exist "!WT_EXE!" (
        "!WT_EXE!" -d "%~dp0." cmd /k """%~f0"""
        exit /b 0
    )
)

if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" -u "%~dp0start_pp2_ngram.py"
endlocal

@echo off
REM start_127k.bat — GPU1 mem=0.948 ctx=127k (max single-GPU MTP n=3, 350W)
cd /d "%~dp0"
if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" start_127k.py

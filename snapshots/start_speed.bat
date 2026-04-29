@echo off
REM start_speed.bat — GPU1 MTP n=6 ctx=90k mem=0.948 350W — peak decode ~64.5 tok/s
cd /d "%~dp0"
if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" start_speed.py

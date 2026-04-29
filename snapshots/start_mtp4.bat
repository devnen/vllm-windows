@echo off
REM start_mtp4.bat — GPU1 MTP n=4 ctx=120k mem=0.948 — best decode TPS (~58)
cd /d "%~dp0"
if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" start_mtp4.py

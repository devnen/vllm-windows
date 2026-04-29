@echo off
if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" "%~dp0start_gpu0_50k.py" %*

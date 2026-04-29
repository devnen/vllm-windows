@echo off
REM stop_vllm.bat — kill any vLLM server on ports 5000-5010 + sweep EngineCore/APIServer children
cd /d "%~dp0"
if "%VLLM_WINDOWS_VENV%"=="" set "VLLM_WINDOWS_VENV=%~dp0..\venv"
"%VLLM_WINDOWS_VENV%\Scripts\python.exe" "%~dp0stop_vllm.py"

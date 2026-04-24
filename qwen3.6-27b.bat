@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] venv not found at %VENV_PYTHON%
    exit /b 1
)

title Qwen3.6-27b vLLM

echo === GPU state ===
nvidia-smi --query-gpu=index,name,power.limit,memory.used,memory.total --format=csv
echo.

"%VENV_PYTHON%" "%SCRIPT_DIR%start_qwen.py" %*
set "RC=%errorlevel%"

echo.
echo Server exited with code %RC%. Press any key to close.
pause >nul
exit /b %RC%

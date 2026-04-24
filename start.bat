@echo off
REM vLLM for Windows launcher (prebuilt wheel 0.11.0+cu124)
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
set "VLLM_EXE=%SCRIPT_DIR%venv\Scripts\vllm.exe"
set "PYTHONIOENCODING=utf-8"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] venv not found at %VENV_PYTHON%
    echo Run the installer to create venv and install vllm wheel.
    exit /b 1
)

REM cd away from repo root to avoid vllm\ source dir shadowing installed package
cd /d "%SCRIPT_DIR%venv"

echo.
echo === GPU info ===
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
echo.
echo === Versions ===
"%VENV_PYTHON%" -c "import torch, vllm; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), 'x'+str(torch.cuda.device_count())); print('vllm', vllm.__version__)"
echo.

if "%~1"=="" (
    echo Usage:
    echo   start.bat serve ^<model^> [--tensor-parallel-size 2] [--host 0.0.0.0] [--port 8000] ...
    echo   start.bat ^<any vllm subcommand^> ...
    echo.
    echo Examples:
    echo   start.bat serve Qwen/Qwen2.5-7B-Instruct --tensor-parallel-size 2 --port 8000
    echo   start.bat --help
    echo.
    "%VLLM_EXE%" --help
    exit /b 0
)

"%VLLM_EXE%" %*
exit /b %errorlevel%

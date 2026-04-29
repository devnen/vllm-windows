"""Shared resolution for snapshot scripts.

Each ``start_*.py`` imports VENV / MODEL_PATH / VCVARS from here so users
can override paths via environment variables instead of editing every
snapshot. Resolution order:

* ``VLLM_WINDOWS_VENV`` env var, else repo-root ``venv``.
* ``VLLM_MODEL_DIR`` env var, else repo-root ``models/Qwen3.6-27B-int4-AutoRound``.
* ``VLLM_WINDOWS_VCVARS`` env var, else the most likely VS 2022 install.
* ``VLLM_WINDOWS_LOGS`` env var, else repo-root ``logs``. Created on first use.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VENV = Path(os.environ.get("VLLM_WINDOWS_VENV", str(REPO_ROOT / "venv")))
VLLM_EXE = VENV / "Scripts" / "vllm.exe"

MODEL_PATH = os.environ.get(
    "VLLM_MODEL_DIR",
    str(REPO_ROOT / "models" / "Qwen3.6-27B-int4-AutoRound"),
)


def _find_vcvars() -> str:
    env = os.environ.get("VLLM_WINDOWS_VCVARS")
    if env and Path(env).exists():
        return env
    candidates = [
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return candidates[2]  # community is the most common — return so caller can warn


VCVARS = _find_vcvars()

LOGS_DIR = Path(os.environ.get("VLLM_WINDOWS_LOGS", str(REPO_ROOT / "logs")))
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_path_for(port: int) -> Path:
    return LOGS_DIR / f"vllm_server.{port}.log"

"""Sanity-check: vLLM install, patches applied, GPU present.

Run after install / before launch. Prints a green / yellow / red summary.

Checks:
  1. vLLM importable, version is 0.19.0+devnen.* (or upstream 0.19.0).
  2. Each file in windows_patches/ matches the in-venv copy by sha256.
  3. nvidia-smi reports at least one Ampere+ GPU (sm_86 or higher).
  4. MSVC `cl.exe` resolvable (warn if not — only matters for FlashInfer JIT).

Exit code 0 = all green. 1 = at least one red. 2 = warnings only.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATCHES = REPO / "windows_patches"

PATCH_MAP = {
    "parallel_state.py":            "vllm/distributed/parallel_state.py",
    "cuda_communicator.py":         "vllm/distributed/device_communicators/cuda_communicator.py",
    "base_device_communicator.py":  "vllm/distributed/device_communicators/base_device_communicator.py",
    "gpu_worker.py":                "vllm/v1/worker/gpu_worker.py",
    "qwen3_reasoning_parser.py":    "vllm/reasoning/qwen3_reasoning_parser.py",
    "serving_models.py":            "vllm/entrypoints/openai/models/serving.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def check_vllm(venv: Path) -> tuple[str, str]:
    py = venv / "Scripts" / "python.exe"
    if not py.exists():
        return ("RED", f"no python.exe at {py}")
    try:
        out = subprocess.check_output(
            [str(py), "-c", "import vllm; print(vllm.__version__)"],
            text=True, timeout=30,
        ).strip()
    except subprocess.CalledProcessError as e:
        return ("RED", f"vllm import failed: {e}")
    if "0.19" not in out:
        return ("YEL", f"unexpected version {out!r}, expected 0.19.x")
    return ("GRN", f"vllm {out}")


def check_patches(venv: Path) -> list[tuple[str, str, str]]:
    sp = venv / "Lib" / "site-packages"
    rows = []
    for src_name, dst_rel in PATCH_MAP.items():
        src = PATCHES / src_name
        dst = sp / dst_rel
        if not dst.exists():
            rows.append(("RED", src_name, f"missing in venv: {dst}"))
            continue
        if not src.exists():
            rows.append(("YEL", src_name, "patch source missing in repo"))
            continue
        if sha(src) == sha(dst):
            rows.append(("GRN", src_name, "applied"))
        else:
            rows.append(("RED", src_name, "DIFFERS — patches not applied"))
    return rows


def check_gpu() -> tuple[str, str]:
    if not shutil.which("nvidia-smi"):
        return ("RED", "nvidia-smi not on PATH")
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
            text=True, timeout=10,
        )
    except subprocess.CalledProcessError as e:
        return ("RED", f"nvidia-smi failed: {e}")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if not lines:
        return ("RED", "no GPU reported")
    bad = []
    for line in lines:
        try:
            cc = float(line.split(",")[-1].strip())
        except ValueError:
            cc = 0.0
        if cc < 8.6:
            bad.append(line)
    if bad:
        return ("YEL", f"non-Ampere+ GPU detected: {bad}; this fork was tuned on sm_86")
    return ("GRN", " | ".join(lines))


def check_msvc() -> tuple[str, str]:
    if shutil.which("cl.exe"):
        return ("GRN", "cl.exe on PATH")
    candidates = [
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Tools",
        r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Tools",
    ]
    for c in candidates:
        if Path(c).exists():
            return ("YEL", f"MSVC found at {c} but not on PATH (only matters for FlashInfer)")
    return ("YEL", "MSVC not found — fine for TRITON_ATTN; FlashInfer JIT would fail")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv", default=str(REPO / "venv"))
    args = ap.parse_args()

    venv = Path(args.venv)
    print(f"== verifying {venv} ==\n")

    rows: list[tuple[str, str, str]] = []
    rows.append(("vllm",) + check_vllm(venv))
    for src, lvl, msg in check_patches(venv):
        rows.append(("patch:" + src, lvl, msg))
    rows.append(("gpu",) + check_gpu())
    rows.append(("msvc",) + check_msvc())

    bad_any = any(lvl == "RED" for _, lvl, _ in rows)
    yellow = any(lvl == "YEL" for _, lvl, _ in rows)
    width = max(len(name) for name, *_ in rows) + 2
    for name, lvl, msg in rows:
        sym = {"GRN": "OK ", "YEL": "WRN", "RED": "ERR"}[lvl]
        print(f"  [{sym}] {name.ljust(width)} {msg}")

    if bad_any:
        print("\nFAIL — fix RED items before launching.")
        return 1
    if yellow:
        print("\nOK with warnings — review WRN items.")
        return 2
    print("\nALL GREEN — ready to launch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

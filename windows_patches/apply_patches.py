"""Overlay the windows_patches/ files onto an installed vLLM venv.

Use this when you've installed the SystemPanic wheel (or the unpatched
upstream) into a venv and want to apply the devnen Windows patches without
reinstalling. Idempotent — running twice is a no-op.

Usage:
    python windows_tools/apply_patches.py --venv C:\\path\\to\\venv

The --venv flag is optional; default is ../venv relative to repo root.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATCHES = REPO / "windows_patches"

# Map: source file in windows_patches/  ->  destination relative to venv site-packages.
MAP = {
    "parallel_state.py":            "vllm/distributed/parallel_state.py",
    "cuda_communicator.py":         "vllm/distributed/device_communicators/cuda_communicator.py",
    "base_device_communicator.py":  "vllm/distributed/device_communicators/base_device_communicator.py",
    "gpu_worker.py":                "vllm/v1/worker/gpu_worker.py",
    "qwen3_reasoning_parser.py":    "vllm/reasoning/qwen3_reasoning_parser.py",
    "serving_models.py":            "vllm/entrypoints/openai/models/serving.py",
}


def find_site_packages(venv: Path) -> Path:
    candidates = [
        venv / "Lib" / "site-packages",
        venv / "lib" / "site-packages",
    ]
    for c in candidates:
        if (c / "vllm" / "__init__.py").exists():
            return c
    raise SystemExit(f"[apply_patches] no vllm install found under {venv}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv", default=str(REPO / "venv"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    venv = Path(args.venv)
    if not venv.exists():
        print(f"[apply_patches] venv not found: {venv}", file=sys.stderr)
        return 1

    sp = find_site_packages(venv)
    print(f"[apply_patches] target: {sp}")

    changed = 0
    for src_name, dst_rel in MAP.items():
        src = PATCHES / src_name
        dst = sp / dst_rel
        if not src.exists():
            print(f"  [skip] missing patch source: {src}")
            continue
        if not dst.exists():
            print(f"  [skip] no upstream file at: {dst}")
            continue
        if src.read_bytes() == dst.read_bytes():
            print(f"  [ok ] {dst_rel}  (already patched)")
            continue
        if args.dry_run:
            print(f"  [DRY] would patch {dst_rel}")
        else:
            backup = dst.with_suffix(dst.suffix + ".upstream.bak")
            if not backup.exists():
                shutil.copy2(dst, backup)
            shutil.copy2(src, dst)
            print(f"  [patch] {dst_rel}")
            changed += 1

    print(f"[apply_patches] done. {changed} file(s) updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

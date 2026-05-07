# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Repackage SystemPanic vLLM wheel as 0.19.0+devnen.<N>.

Takes the upstream wheel, overlays the patched files from this folder
into the embedded ``vllm/`` tree, bumps the version, recomputes RECORD
sha256+size for every modified entry, and writes a new wheel.

Idempotent for a given (input wheel, --tag) pair.

Usage:
    python windows_patches/repackage_wheel.py \
        --in   <path-to-systempanic.whl> \
        --tag  devnen.1 \
        --out  dist/

Output filename:
    vllm-0.19.0+devnen.1-cp312-cp312-win_amd64.whl
    (cu124 / cu126 / etc. suffix stripped from local-version since the
    devnen tag is the meaningful identifier; the binary blobs inside
    are identical to the upstream wheel.)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
import zipfile
from pathlib import Path

PATCHES_DIR = Path(__file__).resolve().parent

# Map of in-wheel path -> our local mirror copy.
# Wheel paths are relative to the wheel root (forward slashes).
PATCH_MAP = {
    "vllm/distributed/parallel_state.py": PATCHES_DIR / "parallel_state.py",
    "vllm/distributed/device_communicators/cuda_communicator.py": PATCHES_DIR
    / "cuda_communicator.py",
    "vllm/distributed/device_communicators/base_device_communicator.py": PATCHES_DIR
    / "base_device_communicator.py",
    "vllm/v1/worker/gpu_worker.py": PATCHES_DIR / "gpu_worker.py",
    "vllm/reasoning/qwen3_reasoning_parser.py": PATCHES_DIR
    / "qwen3_reasoning_parser.py",
    "vllm/entrypoints/openai/models/serving.py": PATCHES_DIR / "serving_models.py",
    # Windows-only fixups for v1 multiproc executor + ZMQ ipc transport.
    # Required for any multi-worker path (PP>=2, multi-engine) on Windows.
    "vllm/utils/network_utils.py": PATCHES_DIR / "network_utils.py",
    "vllm/v1/executor/multiproc_executor.py": PATCHES_DIR / "multiproc_executor.py",
}


def b64sha(data: bytes) -> str:
    return (
        "sha256="
        + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True, help="upstream .whl path")
    ap.add_argument(
        "--tag", default="devnen.1", help="local-version tag (default: devnen.1)"
    )
    ap.add_argument("--out", default=str(Path("dist")), help="output directory")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[repack] ERROR: input wheel not found: {src}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Verify all patch source files exist.
    for wheel_path, local in PATCH_MAP.items():
        if not local.exists():
            print(f"[repack] ERROR: patch source missing: {local}", file=sys.stderr)
            return 1

    # Compute new filename: vllm-0.19.0+<tag>-cp312-cp312-win_amd64.whl
    new_version = f"0.19.0+{args.tag}"
    out_name = f"vllm-{new_version}-cp312-cp312-win_amd64.whl"
    dst = out_dir / out_name

    # We must rewrite METADATA, RECORD, and rename the .dist-info folder.
    # Strategy: stream-copy entries, swap or modify as needed, accumulate RECORD.
    print(f"[repack] reading {src.name} ({src.stat().st_size / 1024 / 1024:.1f} MiB)")

    with zipfile.ZipFile(src, "r") as zin:
        names = zin.namelist()
        # Find the dist-info folder name (e.g. "vllm-0.19.0+cu124.dist-info")
        dist_info_dirs = sorted(
            {
                n.split("/", 1)[0]
                for n in names
                if n.endswith(".dist-info")
                or "/.dist-info" in n
                or n.split("/", 1)[0].endswith(".dist-info")
            }
        )
        old_dist_info = next(n for n in dist_info_dirs if n.endswith(".dist-info"))
        new_dist_info = f"vllm-{new_version}.dist-info"
        print(f"[repack] {old_dist_info} -> {new_dist_info}")

        # Build new entries: list of (arcname, data)
        new_entries: list[tuple[str, bytes]] = []
        record_lines: list[str] = []

        for name in names:
            # Skip RECORD; we'll rebuild it last.
            if name == f"{old_dist_info}/RECORD":
                continue

            data = zin.read(name)
            new_name = name

            # Rename dist-info folder.
            if name.startswith(old_dist_info + "/") or name == old_dist_info:
                new_name = new_dist_info + name[len(old_dist_info) :]

            # Apply patches.
            if name in PATCH_MAP:
                data = PATCH_MAP[name].read_bytes()
                print(f"[repack]   patch: {name} ({len(data)} bytes)")

            # Bump version in METADATA.
            if new_name == f"{new_dist_info}/METADATA":
                text = data.decode("utf-8")
                # Replace the Version: line.
                lines = text.split("\n")
                for i, ln in enumerate(lines):
                    if ln.startswith("Version:"):
                        lines[i] = f"Version: {new_version}"
                        break
                # Append a notice in the description.
                notice = (
                    "\n\n## Modified by devnen/vllm-windows\n\n"
                    "This wheel is a repackaging of the SystemPanic/vllm-windows\n"
                    "0.19.0 wheel with the following patches applied:\n\n"
                    "1. CPU-relay for Gloo collectives (Windows has no NCCL).\n"
                    "2. Qwen3 reasoning parser fix (mirror of upstream PR #35687).\n"
                    "3. Hardwired wildcard model name in the OpenAI server.\n"
                    "4. ZMQ ipc:// -> tcp:// fallback on Windows (network_utils).\n"
                    "5. Widen worker pipe isinstance check to _ConnectionBase\n"
                    "   so PP=2 (multiproc_executor) works on Windows.\n\n"
                    "Source diff: https://github.com/devnen/vllm-windows/blob/main/CHANGES_VS_SYSTEMPANIC.md\n"
                    "License: Apache-2.0 (inherited from upstream vLLM).\n"
                )
                text = "\n".join(lines)
                if "Modified by devnen/vllm-windows" not in text:
                    text += notice
                data = text.encode("utf-8")

            new_entries.append((new_name, data))

            # Build RECORD line. Empty dirs / dist-info itself need different handling.
            if not new_name.endswith("/"):
                line = f"{new_name},{b64sha(data)},{len(data)}"
                record_lines.append(line)

        # RECORD entry references itself with empty hash + size.
        record_lines.append(f"{new_dist_info}/RECORD,,")
        record_blob = ("\n".join(record_lines) + "\n").encode("utf-8")
        new_entries.append((f"{new_dist_info}/RECORD", record_blob))

        print(f"[repack] writing {dst}")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
            for arcname, blob in new_entries:
                zout.writestr(arcname, blob)

    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"[repack] done. {dst.name} = {size_mb:.1f} MiB")
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    print(f"[repack] sha256: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

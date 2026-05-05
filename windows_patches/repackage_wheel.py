# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Repackage SystemPanic vLLM wheel with devnen patches applied.

Takes the upstream wheel, overlays the patched files from this folder
into the embedded ``vllm/`` tree, bumps the version, recomputes RECORD
sha256+size for every modified entry, and writes a new wheel.

The version + filename are derived from the input wheel; the local-version
suffix is preserved (e.g. ``+cu126`` or ``+cu132``) and ``.devnen.<N>`` is
appended.

Idempotent for a given (input wheel, --tag) pair.

Usage:
    python windows_patches/repackage_wheel.py \
        --in   <path-to-systempanic.whl> \
        --tag  devnen.1 \
        --out  dist/

Output filenames:
    vllm-0.19.0+cu126.devnen.1-cp312-cp312-win_amd64.whl   (from v0.19.0 input)
    vllm-0.20.0+cu132.devnen.1-cp312-cp312-win_amd64.whl   (from v0.20.0 input)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
import zipfile
from pathlib import Path

PATCHES_DIR = Path(__file__).resolve().parent

# Map of in-wheel path -> our local mirror copy. Each mirror file lives in
# this folder. Mirrors that do not exist on disk are silently skipped, so
# branches that drop a patch (e.g. v0.20.0 dropped CPU-relay because it ships
# with NCCL) just don't include the mirror file.
CANDIDATE_PATCH_MAP: dict[str, Path] = {
    "vllm/distributed/parallel_state.py": PATCHES_DIR / "parallel_state.py",
    "vllm/distributed/device_communicators/cuda_communicator.py": PATCHES_DIR
    / "cuda_communicator.py",
    "vllm/distributed/device_communicators/base_device_communicator.py": PATCHES_DIR
    / "base_device_communicator.py",
    "vllm/v1/worker/gpu_worker.py": PATCHES_DIR / "gpu_worker.py",
    "vllm/reasoning/qwen3_reasoning_parser.py": PATCHES_DIR
    / "qwen3_reasoning_parser.py",
    "vllm/entrypoints/openai/models/serving.py": PATCHES_DIR / "serving_models.py",
}


def b64sha(data: bytes) -> str:
    return (
        "sha256="
        + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    )


def parse_wheel_filename(name: str) -> tuple[str, str, str]:
    """Return (base_version, local_suffix, py_abi_plat).

    Examples:
        vllm-0.19.0-cp312-cp312-win_amd64.whl
            -> ("0.19.0", "", "cp312-cp312-win_amd64")
        vllm-0.20.0+cu132-cp312-cp312-win_amd64.whl
            -> ("0.20.0", "+cu132", "cp312-cp312-win_amd64")
    """
    m = re.match(
        r"^vllm-(?P<base>[^+\-]+)(?P<local>\+[^\-]+)?-(?P<rest>cp\d+-cp\d+-[\w_]+)\.whl$",
        name,
    )
    if not m:
        raise ValueError(f"unrecognized wheel filename: {name}")
    return m.group("base"), m.group("local") or "", m.group("rest")


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

    base_version, local_suffix, py_abi_plat = parse_wheel_filename(src.name)
    # Compose new local-version: keep upstream cu-suffix if present, append .<tag>.
    new_local = (local_suffix + "." + args.tag) if local_suffix else "+" + args.tag
    new_version = f"{base_version}{new_local}"
    out_name = f"vllm-{new_version}-{py_abi_plat}.whl"

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / out_name

    # Build the active patch map by filtering to mirrors that exist on disk.
    patch_map = {k: v for k, v in CANDIDATE_PATCH_MAP.items() if v.exists()}
    if not patch_map:
        print("[repack] ERROR: no patch mirror files found in", PATCHES_DIR, file=sys.stderr)
        return 1
    print(f"[repack] active patches:")
    for k, v in patch_map.items():
        print(f"  - {k}  <-  {v.name}")

    print(f"[repack] reading {src.name} ({src.stat().st_size / 1024 / 1024:.1f} MiB)")

    with zipfile.ZipFile(src, "r") as zin:
        names = zin.namelist()
        # Find the dist-info folder name (e.g. "vllm-0.20.0+cu132.dist-info")
        dist_info_dirs = sorted(
            {
                n.split("/", 1)[0]
                for n in names
                if n.split("/", 1)[0].endswith(".dist-info")
            }
        )
        if not dist_info_dirs:
            print("[repack] ERROR: no .dist-info folder in wheel", file=sys.stderr)
            return 1
        old_dist_info = dist_info_dirs[0]
        new_dist_info = f"vllm-{new_version}.dist-info"
        print(f"[repack] {old_dist_info} -> {new_dist_info}")

        new_entries: list[tuple[str, bytes]] = []
        record_lines: list[str] = []
        applied: list[str] = []
        skipped_identical: list[str] = []

        for name in names:
            if name == f"{old_dist_info}/RECORD":
                continue

            data = zin.read(name)
            new_name = name

            if name.startswith(old_dist_info + "/") or name == old_dist_info:
                new_name = new_dist_info + name[len(old_dist_info) :]

            if name in patch_map:
                patched = patch_map[name].read_bytes()
                # Normalize newlines for comparison; many mirrors are LF on disk
                # while upstream wheels embed LF too, so a byte-equal check is fine.
                if patched == data:
                    skipped_identical.append(name)
                else:
                    data = patched
                    applied.append(name)

            if new_name == f"{new_dist_info}/METADATA":
                text = data.decode("utf-8")
                lines = text.split("\n")
                for i, ln in enumerate(lines):
                    if ln.startswith("Version:"):
                        lines[i] = f"Version: {new_version}"
                        break
                applied_summary = (
                    ", ".join(p.split("/")[-1] for p in applied) or "(none — all upstream-equal)"
                )
                notice = (
                    "\n\n## Modified by devnen/vllm-windows\n\n"
                    f"This wheel is a repackaging of the SystemPanic/vllm-windows\n"
                    f"{base_version} wheel with the devnen Windows patches applied.\n\n"
                    f"Active patches: {applied_summary}\n\n"
                    "Source diff: https://github.com/devnen/vllm-windows/blob/main/CHANGES_VS_SYSTEMPANIC.md\n"
                    "License: Apache-2.0 (inherited from upstream vLLM).\n"
                )
                text = "\n".join(lines)
                if "Modified by devnen/vllm-windows" not in text:
                    text += notice
                data = text.encode("utf-8")

            new_entries.append((new_name, data))

            if not new_name.endswith("/"):
                record_lines.append(f"{new_name},{b64sha(data)},{len(data)}")

        record_lines.append(f"{new_dist_info}/RECORD,,")
        record_blob = ("\n".join(record_lines) + "\n").encode("utf-8")
        new_entries.append((f"{new_dist_info}/RECORD", record_blob))

        print(f"[repack] writing {dst}")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
            for arcname, blob in new_entries:
                zout.writestr(arcname, blob)

    print(f"[repack] applied {len(applied)} patch(es), {len(skipped_identical)} no-op(s)")
    for n in applied:
        print(f"  + {n}")
    for n in skipped_identical:
        print(f"  = {n} (already upstream-equal)")
    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"[repack] done. {dst.name} = {size_mb:.1f} MiB")
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    print(f"[repack] sha256: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

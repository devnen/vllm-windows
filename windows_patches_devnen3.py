"""Repackage vllm-0.19.0+devnen.2 wheel as +devnen.3 with the os.sched_yield
Windows-portability fix overlaid onto vllm/distributed/utils.py.

Usage:
    python windows_patches_devnen3.py \
        --in dist/vllm-0.19.0+devnen.2-cp312-cp312-win_amd64.whl \
        --out dist/

Output: dist/vllm-0.19.0+devnen.3-cp312-cp312-win_amd64.whl
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
PATCH_MAP = {
    "vllm/distributed/utils.py": REPO / "vllm" / "distributed" / "utils.py",
}
NEW_VERSION = "0.19.0+devnen.3"


def b64sha(data: bytes) -> str:
    return (
        "sha256="
        + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[repack] ERROR: {src} not found", file=sys.stderr)
        return 1
    for wheel_path, local in PATCH_MAP.items():
        if not local.exists():
            print(f"[repack] ERROR: patch source missing: {local}", file=sys.stderr)
            return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"vllm-{NEW_VERSION}-cp312-cp312-win_amd64.whl"

    with zipfile.ZipFile(src, "r") as zin:
        names = zin.namelist()
        old_dist_info = next(
            n.split("/", 1)[0]
            for n in names
            if n.split("/", 1)[0].endswith(".dist-info")
        )
        new_dist_info = f"vllm-{NEW_VERSION}.dist-info"
        print(f"[repack] {old_dist_info} -> {new_dist_info}")

        new_entries: list[tuple[str, bytes]] = []
        record_lines: list[str] = []

        for name in names:
            if name == f"{old_dist_info}/RECORD":
                continue
            data = zin.read(name)
            new_name = name
            if name.startswith(old_dist_info + "/") or name == old_dist_info:
                new_name = new_dist_info + name[len(old_dist_info):]
            if name in PATCH_MAP:
                data = PATCH_MAP[name].read_bytes()
                print(f"[repack]   patch: {name} ({len(data)} bytes)")
            if new_name == f"{new_dist_info}/METADATA":
                text = data.decode("utf-8")
                lines = text.split("\n")
                for i, ln in enumerate(lines):
                    if ln.startswith("Version:"):
                        lines[i] = f"Version: {NEW_VERSION}"
                        break
                text = "\n".join(lines)
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

    size_mb = dst.stat().st_size / 1024 / 1024
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    print(f"[repack] done. {dst.name} = {size_mb:.1f} MiB")
    print(f"[repack] sha256: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

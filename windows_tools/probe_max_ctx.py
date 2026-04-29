"""Auto-probe the maximum context length the current config can serve.

Trick: launch vLLM with ``--max-model-len=200000`` (deliberately too high).
The engine's KV-pool allocator will refuse and print:

    ValueError: ... estimated maximum model length is N

Parse N from stderr, kill the process, return N. Set ``--max-model-len``
in your snapshot to ~99% of N.

Usage:
    python windows_tools/probe_max_ctx.py --snapshot snapshots/start_speed.py

The snapshot is launched once with VLLM_PROBE_MAX_CTX=1 in env so the
caller can short-circuit if it wants. Default behaviour is unchanged.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERN = re.compile(r"estimated maximum model length is (\d+)", re.IGNORECASE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="path to start_*.py")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    snap = Path(args.snapshot)
    if not snap.exists():
        print(f"[probe] snapshot not found: {snap}", file=sys.stderr)
        return 1

    print(f"[probe] launching {snap.name} with VLLM_PROBE_MAX_CTX=1, max-model-len=200000")
    print(f"[probe] reading stderr until 'estimated maximum model length is N' appears...")

    env_extra = "set VLLM_PROBE_MAX_CTX=1 && "  # snapshot can branch on this
    cmd = f'{env_extra}python "{snap}"'
    try:
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except OSError as e:
        print(f"[probe] launch failed: {e}", file=sys.stderr)
        return 1

    found = None
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="")
            m = PATTERN.search(line)
            if m:
                found = int(m.group(1))
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    if found is None:
        print("\n[probe] no 'estimated maximum model length' line seen — config probably booted OK")
        return 2
    print(f"\n[probe] estimated maximum model length: {found}")
    print(f"[probe] suggested --max-model-len: {int(found * 0.99)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

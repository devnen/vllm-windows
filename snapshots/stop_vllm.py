"""Stop any vLLM server listening on ports 5000-5010.

Kills the direct port owner (pid tree) and sweeps EngineCore/APIServer pids
logged in vllm_server*.log files in this directory.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import os

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PORTS = range(5000, 5011)
LOG_DIR = Path(os.environ.get("VLLM_WINDOWS_LOGS", str(REPO_ROOT / "logs")))
LOG_GLOB = "vllm_server*.log"


def port_owner_pids(port: int) -> list[int]:
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    return sorted(pids)


def kill_pid_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return False
        except OSError:
            return True


def main() -> int:
    killed_any = False
    for port in PORTS:
        for pid in port_owner_pids(port):
            print(f"[stop] killing pid {pid} (was on :{port})")
            kill_pid_tree(pid)
            killed_any = True

    swept = set()
    log_paths = list(LOG_DIR.glob(LOG_GLOB)) if LOG_DIR.exists() else []
    log_paths += list(HERE.glob(LOG_GLOB))  # legacy: logs co-located with snapshots
    for log in log_paths:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.findall(r"(?:EngineCore|APIServer) pid=(\d+)", text):
            swept.add(int(m))
    for pid in sorted(swept):
        kill_pid_tree(pid)
    if swept:
        print(f"[stop] swept {len(swept)} EngineCore/APIServer pids: {sorted(swept)}")

    deadline = time.time() + 15
    while time.time() < deadline:
        if all(port_free(p) for p in PORTS):
            break
        time.sleep(0.5)

    busy = [p for p in PORTS if not port_free(p)]
    if busy:
        print(f"[stop] ports still busy: {busy}", file=sys.stderr)
        return 1

    if not killed_any and not swept:
        print("[stop] no vLLM server found on ports 5000-5010")
    else:
        print("[stop] all vLLM ports clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())

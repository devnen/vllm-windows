"""Kill any vllm server on a port and relaunch a snapshot in the background.

Sweeps every ``EngineCore pid=N`` / ``APIServer pid=N`` line from the
matching log file because vLLM's API-server PID does NOT always cascade
to the EngineCore subprocess on Windows — orphans hold the ZMQ port and
break the next launch with ``Address in use (addr='tcp://127.0.0.1:459NN')``.

Usage:
    python windows_tools/tune_restart.py --snapshot snapshots/start_speed.py [--port 5001]
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def port_owner_pid(port: int) -> list[int]:
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids: set[int] = set()
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
        s.settimeout(0.4)
        try:
            s.connect(("127.0.0.1", port))
            return False
        except OSError:
            return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="path to start_*.py")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--log", default=None, help="log file to sweep PIDs from (default: <repo>/logs/vllm_server.<port>.log)")
    ap.add_argument("--venv", default=str(REPO / "venv"))
    args = ap.parse_args()

    snapshot = Path(args.snapshot).resolve()
    if not snapshot.exists():
        print(f"[tune] snapshot not found: {snapshot}", file=sys.stderr)
        return 1
    venv_py = Path(args.venv) / "Scripts" / "python.exe"
    if not venv_py.exists():
        print(f"[tune] python.exe not found at {venv_py}", file=sys.stderr)
        return 1
    log_path = Path(args.log) if args.log else REPO / "logs" / f"vllm_server.{args.port}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Kill direct port owner.
    for pid in port_owner_pid(args.port):
        print(f"[tune] killing pid {pid} (was on :{args.port})")
        kill_pid_tree(pid)
    # Sweep every EngineCore / APIServer PID from the previous log.
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        pids = {int(m) for m in re.findall(r"(?:EngineCore|APIServer) pid=(\d+)", text)}
        for pid in sorted(pids):
            kill_pid_tree(pid)
        if pids:
            print(f"[tune] swept {len(pids)} pids from log: {sorted(pids)}")

    deadline = time.time() + 30
    while time.time() < deadline and not port_free(args.port):
        time.sleep(0.5)
    if not port_free(args.port):
        print(f"[tune] port {args.port} still busy after 30s", file=sys.stderr)
        return 1

    log_path.write_text("", encoding="utf-8")
    log_f = open(log_path, "a", encoding="utf-8", buffering=1)
    print(f"[tune] launching {snapshot.name} -> {log_path}")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    proc = subprocess.Popen(
        [str(venv_py), "-u", str(snapshot)],
        cwd=str(snapshot.parent),
        stdout=log_f, stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    print(f"[tune] pid={proc.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

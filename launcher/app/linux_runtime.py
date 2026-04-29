"""Remote control of the popos vLLM box over SSH.

Detection: docker inspect of the two known container names → parse vLLM cmd
vector for --tensor-parallel-size, --max-model-len, --language-model-only,
num_speculative_tokens, --kv-cache-dtype. Match against LinuxConfig list.

Launch: invoke the per-config .sh script in the background. The script's
own EXIT trap handles `docker compose down` + power-cap reset on shutdown.

Unload: SIGTERM the launch script (fires its trap). Fallback: docker
compose down in the project's compose dir.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

from .config import LinuxConfig

CREATE_NO_WINDOW = 0x08000000


def _ssh_cli() -> list[str]:
    root = os.environ.get("CC_PORTABLE_ROOT", r"C:\_projects\claude-portable")
    return ["python", os.path.join(root, "mcp-servers", "ssh-pkg", "ssh.py")]


def ssh_exec(host: str, user: str, password: str, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a remote shell command. Returns (exit_code, stdout, stderr)."""
    args = _ssh_cli() + [
        "--raw", "--host", host, "--user", user, "--password", password,
        "exec", cmd,
    ]
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return -1, "", "ssh timeout"
    except Exception as e:
        return -1, "", f"ssh launch error: {e}"
    raw = r.stdout or ""
    # ssh-pkg --raw still wraps in JSON; parse
    try:
        j = json.loads(raw)
        return int(j.get("exit_code", -1)), j.get("stdout", "") or "", j.get("stderr", "") or ""
    except Exception:
        return r.returncode, raw, r.stderr or ""


@dataclass
class RemoteProc:
    container: str           # "tp2" or "1gpu"
    container_name: str
    tp: int
    ctx: int
    vision_on: bool
    mtp_n: int | None
    kv_dtype: str
    matched_id: str | None = None


def _parse_cmd_vector(cmd_json: str) -> dict | None:
    cmd_json = cmd_json.strip()
    if not cmd_json or cmd_json == "null":
        return None
    try:
        v = json.loads(cmd_json)
    except Exception:
        return None
    if not isinstance(v, list):
        return None
    out: dict = {"vision_on": True}
    i = 0
    while i < len(v):
        a = v[i]
        if a == "--tensor-parallel-size" and i + 1 < len(v):
            try: out["tp"] = int(v[i+1])
            except Exception: pass
            i += 2; continue
        if a == "--max-model-len" and i + 1 < len(v):
            try: out["ctx"] = int(v[i+1])
            except Exception: pass
            i += 2; continue
        if a == "--language-model-only":
            out["vision_on"] = False
            i += 1; continue
        if a == "--kv-cache-dtype" and i + 1 < len(v):
            out["kv_dtype"] = str(v[i+1])
            i += 2; continue
        if a == "--speculative-config" and i + 1 < len(v):
            try:
                spec = json.loads(v[i+1])
                if isinstance(spec, dict):
                    out["mtp_n"] = spec.get("num_speculative_tokens")
            except Exception:
                pass
            i += 2; continue
        i += 1
    return out


def detect_running(host: str, user: str, password: str,
                   shared: dict, configs: list[LinuxConfig]) -> dict[str, RemoteProc]:
    """Return {config_id: RemoteProc} for every known container that's up."""
    name_tp2 = shared.get("container_name_tp2", "vllm-qwen36-27b-turbo-tp2")
    name_1gpu = shared.get("container_name_1gpu", "vllm-qwen36-27b-turbo-1gpu")
    pairs = (("tp2", name_tp2), ("1gpu", name_1gpu))
    parts = []
    for tag, name in pairs:
        parts.append(
            f"echo '#####{tag}#####'; "
            f"docker inspect {name} --format '{{{{json .Config.Cmd}}}}' 2>/dev/null || echo MISSING"
        )
    cmd = " ; ".join(parts)
    code, out, _err = ssh_exec(host, user, password, cmd, timeout=15)
    if code != 0 and not out:
        return {}
    result: dict[str, RemoteProc] = {}
    sections = re.split(r"#####(\w+)#####\n?", out)
    # sections = ['', tag, body, tag, body, ...]
    for tag, body in zip(sections[1::2], sections[2::2]):
        name = name_tp2 if tag == "tp2" else name_1gpu
        body = body.strip()
        if not body or body == "MISSING":
            continue
        info = _parse_cmd_vector(body)
        if not info:
            continue
        proc = RemoteProc(
            container=tag, container_name=name,
            tp=int(info.get("tp", 1)),
            ctx=int(info.get("ctx", 0)),
            vision_on=bool(info.get("vision_on", True)),
            mtp_n=info.get("mtp_n"),
            kv_dtype=str(info.get("kv_dtype", "")),
        )
        # match against configs: container + tp + ctx + vision + (mtp_n if both set) + (kv_dtype if both set)
        best = None
        for c in configs:
            if c.container != proc.container: continue
            if c.tp != proc.tp: continue
            if c.ctx != proc.ctx: continue
            if c.vision_on != proc.vision_on: continue
            if c.mtp_n is not None and proc.mtp_n is not None and c.mtp_n != proc.mtp_n:
                continue
            if proc.kv_dtype and c.kv_dtype and c.kv_dtype != proc.kv_dtype:
                continue
            best = c.id; break
        if best is None:
            # looser match: container + tp + ctx
            for c in configs:
                if c.container == proc.container and c.tp == proc.tp and c.ctx == proc.ctx:
                    best = c.id; break
        proc.matched_id = best
        if best:
            result[best] = proc
    return result


def health_check(host: str, user: str, password: str, port: int) -> bool:
    code, out, _ = ssh_exec(
        host, user, password,
        f"curl -sf --max-time 3 http://localhost:{port}/v1/models > /dev/null && echo OK",
        timeout=8,
    )
    return code == 0 and out.strip().endswith("OK")


def start_config(host: str, user: str, password: str, cfg: LinuxConfig) -> tuple[bool, str]:
    """Fire the launch script in the background. Output goes to /tmp/vllm-launcher-<id>.log.

    The script does its own port-collision check; if another vLLM is up on the
    same port the script exits 1 and we surface that.
    """
    if not cfg.launch_sh:
        return False, f"No launch script for {cfg.id}"
    log = f"/tmp/vllm-launcher-{cfg.id}.log"
    # `setsid` + `nohup` + `disown` so the process survives the SSH session close.
    cmd = (
        f"rm -f {log}; "
        f"setsid nohup bash {cfg.launch_sh} > {log} 2>&1 < /dev/null & disown; "
        f"sleep 1; "
        f"if [ -s {log} ]; then head -c 4000 {log}; fi; "
        f"pgrep -f 'launch-qwen3.6-turbo' | head -1"
    )
    code, out, err = ssh_exec(host, user, password, cmd, timeout=20)
    if code != 0:
        return False, (err or out or "ssh failed").strip()
    if "ERROR:" in out or "already in use" in out:
        return False, out.strip()
    return True, f"Launched {cfg.id} (log: {log})"


def stop_running(host: str, user: str, password: str, shared: dict) -> tuple[bool, str]:
    """Stop whatever vLLM is up. SIGTERMs any background launch-*.sh (so its
    EXIT trap fires → docker compose down + power reset), THEN unconditionally
    runs `docker compose down` to catch containers started directly via
    `docker compose up -d` without the launcher script.

    The pgrep pattern is anchored on `/launch-qwen3.6-turbo-vN.sh` (full path
    with leading slash + version + .sh tail) so it cannot self-match the
    remote shell that's running this command.
    """
    proj = shared.get("project_dir", "/home/nenad/_projects/vllm-turbo")
    pattern = r"/launch-qwen3\.6-turbo-v[0-9a-z]+\.sh"
    cmd = f"""set +e
RES=""
SELF=$$
PIDS=$(pgrep -f '{pattern}' 2>/dev/null | grep -vw "$SELF" || true)
if [ -n "$PIDS" ]; then
  echo "$PIDS" | xargs -r kill -TERM 2>/dev/null
  RES="$RES termed($(echo $PIDS | tr '\\n' ',' | sed 's/,$//'))"
  for i in $(seq 1 15); do
    REMAIN=$(pgrep -f '{pattern}' 2>/dev/null | grep -vw "$SELF" || true)
    [ -z "$REMAIN" ] && break
    sleep 1
  done
fi
if docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep -q '^vllm-qwen36-27b-turbo-'; then
  cd {proj}/compose 2>/dev/null && docker compose down 2>&1 | tail -3
  RES="$RES compose-down"
fi
# Failsafe: if a stray container survives (no compose file matched), force-stop.
STRAY=$(docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep '^vllm-qwen36-27b-turbo-' || true)
if [ -n "$STRAY" ]; then
  echo "$STRAY" | xargs -r docker stop -t 30 >/dev/null 2>&1
  RES="$RES force-stopped($STRAY)"
fi
echo "DONE:${{RES:- nothing-to-stop}}"
"""
    code, out, err = ssh_exec(host, user, password, cmd, timeout=120)
    body = (out or "") + (("\n" + err) if err else "")
    last = "no output"
    for line in reversed(body.strip().splitlines()):
        if line.strip():
            last = line.strip(); break
    return code == 0, last


def fetch_log_tail(host: str, user: str, password: str, cfg_id: str, lines: int = 60) -> str:
    code, out, _ = ssh_exec(
        host, user, password,
        f"tail -n {lines} /tmp/vllm-launcher-{cfg_id}.log 2>/dev/null || echo '(no log)'",
        timeout=10,
    )
    return out or ""


# --- power management ----------------------------------------------------

def ping_alive(ip: str, timeout_s: int = 2) -> bool:
    """Return True iff `ip` answers a single ICMP echo within `timeout_s` seconds.

    Uses the local OS ping. Works on Windows and Linux.
    """
    import platform
    sys_ = platform.system().lower()
    if sys_.startswith("win"):
        # Windows ping uses -n count, -w timeout-ms
        args = ["ping", "-n", "1", "-w", str(timeout_s * 1000), ip]
    else:
        args = ["ping", "-c", "1", "-W", str(timeout_s), ip]
    try:
        r = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout_s + 2,
            creationflags=CREATE_NO_WINDOW,
        )
        return r.returncode == 0
    except Exception:
        return False


def wait_until_offline(ip: str, max_seconds: int = 120) -> bool:
    """Block until `ip` stops responding to ping, or timeout. Returns True if offline."""
    import time
    deadline = time.monotonic() + max_seconds
    consecutive_misses = 0
    while time.monotonic() < deadline:
        if ping_alive(ip, timeout_s=2):
            consecutive_misses = 0
        else:
            consecutive_misses += 1
            if consecutive_misses >= 3:
                return True
        time.sleep(1.0)
    return False


def wait_until_online(ip: str, max_seconds: int = 180) -> bool:
    """Block until `ip` answers ping, or timeout. Returns True if online."""
    import time
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        if ping_alive(ip, timeout_s=2):
            return True
        time.sleep(2.0)
    return False


def shutdown_box(host: str, user: str, password: str, shared: dict,
                 progress=None) -> tuple[bool, str]:
    """Graceful shutdown: stop_running -> enable WOL on NIC -> sudo shutdown -> ping wait.

    `progress` is an optional callable(str) for live status updates.
    Returns (ok, summary).
    """
    def _p(s: str):
        if progress: progress(s)

    _p("Stopping any running vLLM...")
    ok, msg = stop_running(host, user, password, shared)
    if not ok:
        return False, f"stop_running failed: {msg}"
    _p(f"vllm stopped ({msg})")

    nic = shared.get("nic_name", "enp34s0")
    _p(f"Enabling WOL (magic) on {nic}...")
    code, out, err = ssh_exec(
        host, user, password,
        f"sudo -n ethtool -s {nic} wol g 2>&1 && sudo -n ethtool {nic} 2>&1 | grep -i 'Wake-on'",
        timeout=10,
    )
    if code != 0:
        # don't fail the whole shutdown — just warn
        _p(f"WOL enable WARNING: {(out or err).strip()[:120]}")
    else:
        _p((out or err).strip().splitlines()[-1] if (out or err) else "WOL enabled")

    _p("Issuing sudo shutdown now...")
    # Fire shutdown asynchronously so ssh doesn't error when sshd dies.
    code, out, err = ssh_exec(
        host, user, password,
        "(sleep 1 && sudo -n /sbin/shutdown now) >/dev/null 2>&1 & disown; echo SCHEDULED",
        timeout=10,
    )
    if "SCHEDULED" not in (out or ""):
        return False, f"shutdown command failed: {(err or out)[:200]}"

    _p("Waiting for box to go offline (ping)...")
    if not wait_until_offline(host, max_seconds=120):
        return False, f"box still pings after 120s — shutdown may have hung"
    _p(f"Box {host} confirmed OFFLINE.")
    return True, f"{host} is offline."


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255",
                ports: tuple[int, ...] = (9, 7)) -> tuple[bool, str]:
    """Send WOL magic packet to `broadcast` on `ports` (UDP).

    Sends to multiple common WOL ports (9 and 7) for robustness. Returns
    (sent_ok, message). Does NOT verify the box came online — caller
    should poll ping_alive separately.
    """
    import socket
    mac_clean = mac.replace(":", "").replace("-", "").lower()
    if len(mac_clean) != 12:
        return False, f"invalid MAC: {mac}"
    try:
        payload = bytes.fromhex("ff" * 6 + mac_clean * 16)
    except ValueError:
        return False, f"could not parse MAC: {mac}"
    sent = 0
    last_err = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for p in ports:
            try:
                s.sendto(payload, (broadcast, p))
                sent += 1
            except Exception as e:
                last_err = str(e)
        s.close()
    except Exception as e:
        return False, f"socket error: {e}"
    if sent == 0:
        return False, last_err or "no packets sent"
    return True, f"sent {sent} magic packet(s) to {broadcast}:{ports} for {mac}"

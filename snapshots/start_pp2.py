"""PP=2 variant — uses BOTH 3090s so KV cache fits a much larger context.

Measured on 2x RTX 3090, Qwen3.6-27B Lorbus AutoRound INT4, fp8_e4m3 KV,
TRITON_ATTN, gpu-memory-utilization=0.92:
  - KV pool: 169,344 tokens total.
  - ctx=160000: 43.5 tok/s decode, TTFT 0.76 s (committed snapshot).
  - ctx=128000: 43.2 tok/s decode, TTFT 0.87 s.
  - ctx=96000:  43.1 tok/s decode, TTFT 2.22 s (first-run cold cache).

Spec-decode disabled on vLLM 0.19.0 because every option breaks with PP>1:
  - MTP          -> NotImplementedError on Qwen3-Next (documented).
  - ngram        -> 'GPUModelRunner' object has no attribute 'drafter'.
  - draft-model  -> unsupported with PP>1 since vLLM 0.15.

Port 5002 so it can coexist with the 72-tok/s MTP baseline on port 5001.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
from _common import VENV, VLLM_EXE, MODEL_PATH, VCVARS, log_path_for
SERVED_NAME = "qwen3.6-27b-autoround"
HOST = "0.0.0.0"
PORT = 5002  # baseline 72-tok/s server owns 5001

# ---- Parallelism ------------------------------------------------------------
TP = 1
PP = 2  # split model across GPU0 + GPU1 -> free up KV space for context
USE_NGRAM = False  # Drafter pre-init patch unblocks boot but PP+ngram trips an
                    # assertion in _prepare_inputs (total_num_scheduled_tokens>0)
                    # — structural scheduler bug, not patchable inline.
NGRAM_NUM_SPEC_TOKENS = 5
NGRAM_PROMPT_LOOKUP_MAX = 4
NGRAM_PROMPT_LOOKUP_MIN = 2

# ---- Memory + context -------------------------------------------------------
# KV pool at these settings holds ~169k tokens. 160k leaves ~9k headroom for
# the prompt. If you change GPU_MEM_UTIL, KV_CACHE_DTYPE, or the model, boot
# once and re-read the "GPU KV cache size" line from the log before raising.
CTX = 160000
GPU_MEM_UTIL = 0.92  # PP=2 baseline; 0.93 saved measurably nothing (KV pool same)
KV_CACHE_DTYPE = "fp8_e4m3"
MAX_NUM_BATCHED_TOKENS = 4128

ENFORCE_EAGER = False
ENABLE_VISION = False
def msvc_env() -> dict:
    if not Path(VCVARS).exists():
        print(f"[warn] vcvars64.bat not found at {VCVARS}")
        return {}
    out = subprocess.check_output(
        f'cmd /S /C ""{VCVARS}" && set"',
        text=True, errors="replace",
    )
    env = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host if host != "0.0.0.0" else "127.0.0.1", port))
            return True
        except OSError:
            return False


def main() -> int:
    if not VLLM_EXE.exists():
        print(f"[ERROR] vllm.exe not found at {VLLM_EXE}", file=sys.stderr)
        return 1
    if not Path(MODEL_PATH).exists():
        print(f"[ERROR] Model dir not found: {MODEL_PATH}", file=sys.stderr)
        return 1
    if port_in_use(HOST, PORT):
        print(f"[ERROR] Port {PORT} already in use.", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env.update(msvc_env())
    env["CUDA_VISIBLE_DEVICES"] = "0,1"
    env["VLLM_SLEEP_WHEN_IDLE"] = "1"
    env["VLLM_ENABLE_CUDAGRAPH_GC"] = "1"
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "1"
    env["VLLM_ALLOW_LONG_MAX_MODEL_LEN"] = "1"
    env["VLLM_MARLIN_USE_ATOMIC_ADD"] = "1"
    env["RAY_memory_monitor_refresh_ms"] = "0"
    env["OMP_NUM_THREADS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["VLLM_ATTENTION_BACKEND"] = "TRITON_ATTN"
    env["USE_LIBUV"] = "0"
    env["TORCH_NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["PYTHONFAULTHANDLER"] = "1"
    # Reddit Splinter2121 envs were measured on PP=2 2026-04-25 — regressed
    # decode 40.3 → 39.2 tok/s. Probably Gloo-CPU-relay bound, not compute/mem.

    args = [
        str(VLLM_EXE), "serve", MODEL_PATH,
        f"--served-model-name={SERVED_NAME}",
        "--quantization=auto-round",
        f"--max-model-len={CTX}",
        "--max-num-seqs=1",
        f"--max-num-batched-tokens={MAX_NUM_BATCHED_TOKENS}",
        "--block-size=32",
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--no-scheduler-reserve-full-isl",  # +5k KV pool; decode within noise
        "--enable-auto-tool-choice",
        "--tool-call-parser=qwen3_coder",
        "--reasoning-parser=qwen3",
        f"--kv-cache-dtype={KV_CACHE_DTYPE}",
        f"--tensor-parallel-size={TP}",
        f"--pipeline-parallel-size={PP}",
        f"--gpu-memory-utilization={GPU_MEM_UTIL}",
        "--trust-remote-code",
        "--attention-backend=TRITON_ATTN",
        "--distributed-executor-backend=mp",
        "--no-use-tqdm-on-load",
        f"--host={HOST}",
        f"--port={PORT}",
    ]
    if ENFORCE_EAGER:
        args.append("--enforce-eager")
    if not ENABLE_VISION:
        args.append('--limit-mm-per-prompt={"image":0,"video":0}')
    if USE_NGRAM:
        spec = (
            '{"method":"ngram",'
            f'"num_speculative_tokens":{NGRAM_NUM_SPEC_TOKENS},'
            f'"prompt_lookup_max":{NGRAM_PROMPT_LOOKUP_MAX},'
            f'"prompt_lookup_min":{NGRAM_PROMPT_LOOKUP_MIN}'
            '}'
        )
        args.append(f"--speculative-config={spec}")

    print("=" * 60)
    print(f"vLLM serve: {SERVED_NAME}  (PP=2 + ngram variant)")
    print(f"  Model   : {MODEL_PATH}")
    print(f"  Ctx     : {CTX}  |  TP: {TP}  |  PP: {PP}")
    print(f"  KV dtype: {KV_CACHE_DTYPE}  |  ngram: {USE_NGRAM} (n={NGRAM_NUM_SPEC_TOKENS})")
    print(f"  Listen  : http://{HOST}:{PORT}")
    print("=" * 60)
    print(" ".join(args))
    print("=" * 60, flush=True)

    log_path = HERE / "vllm_server_pp2.log"
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)
    print(f"[launcher] tee stdout -> {log_path} (also streaming to this terminal)")
    proc = subprocess.Popen(
        args, env=env, cwd=str(VENV),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
        text=True, encoding="utf-8", errors="replace",
    )

    import threading
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    def _tee():
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                pass
            log_f.write(line)
    threading.Thread(target=_tee, daemon=True).start()

    def _forward(sig, _frame):
        proc.send_signal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _forward)
    signal.signal(signal.SIGTERM, _forward)

    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())

"""Launch vLLM serving Qwen3.6-27B (Lorbus AutoRound INT4) on Windows.

Native Windows port of the 85-TPS-single-3090 recipe from the Wasif Basharat
2026-04-23 writeup. Because vLLM 0.19.0 on Windows does NOT have TurboQuant KV,
we drop the 3-bit KV path and use fp8_e5m2 instead. The rest of the recipe
transfers: Lorbus AutoRound quant, MTP spec-decode n=3, cudagraphs, Qwen3
reasoning + tool parsers, prefix caching.

Rollback-safe: uses the existing vllm-windows venv (no modifications). All
experimentation lives in this folder.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Reuse the existing Windows vLLM install so this folder stays rollbackable.
from _common import VENV, VLLM_EXE, MODEL_PATH, VCVARS, log_path_for
SERVED_NAME = "qwen3.6-27b-autoround"
HOST = "0.0.0.0"
PORT = 5001  # different from vllm-windows (5000), so both can coexist if needed

# ---- Parallelism ------------------------------------------------------------
# MTP spec-decode is NOT compatible with PP on Qwen3-Next (NotImplementedError
# on startup). So for max tok/s we run TP=1 on a single GPU with MTP. The
# second GPU stays free for other work.
# If you want max context instead, flip to PP=2 MTP=False (no spec-decode).
TP = 1
PP = 1
USE_MTP = True
NUM_SPEC_TOKENS = 4  # retest n=4 at 350W — speed budget different than 250W

# ---- Memory + context -------------------------------------------------------
# Single-card Lorbus weight footprint: ~16.9 GB. With fp8_e5m2 KV and
# gpu-memory-utilization=0.95 we expect ~40-60K tokens of KV. Start ctx modest
# and grow after first successful boot.
CTX = 120000  # MTP n=4 ceiling probe
GPU_MEM_UTIL = 0.948  # GPU1 — vLLM sees free=22.76 GiB after CUDA init → 0.948 ceiling
KV_CACHE_DTYPE = "fp8_e4m3"  # TRITON_ATTN only accepts fp8/fp8_e4m3 (not e5m2).
MAX_NUM_BATCHED_TOKENS = 4128

# ---- Misc -------------------------------------------------------------------
ENFORCE_EAGER = False   # cudagraphs on for decode speedup
ENABLE_VISION = False   # MoonViT tower adds ~0.9 GB; Windows c10d allreduce
                        # can crash during vision profile. Keep off initially.
def msvc_env() -> dict:
    """Capture env vars set by vcvars64.bat so FlashInfer's ninja+cl.exe JIT works.
    Without this, fp8 KV hits a FileNotFoundError when FlashInfer tries to compile
    a new prefill kernel at first request.
    """
    if not Path(VCVARS).exists():
        print(f"[warn] vcvars64.bat not found at {VCVARS} — FlashInfer JIT may fail.")
        return {}
    # Use cmd.exe /S /C so the outer quotes are stripped and inner quotes work.
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
    # Overlay MSVC dev env so FlashInfer can JIT-compile kernels (needed for
    # fp8 KV cache which triggers a new prefill kernel build at first request).
    env.update(msvc_env())
    _world = TP * PP
    # GPU1 only when single-card (leaves GPU0 free for display/other work);
    # both cards when TP/PP > 1.
    env["CUDA_VISIBLE_DEVICES"] = "0,1" if _world > 1 else "1"
    env["VLLM_SLEEP_WHEN_IDLE"] = "1"
    env["VLLM_ENABLE_CUDAGRAPH_GC"] = "1"
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "1"
    env["VLLM_ALLOW_LONG_MAX_MODEL_LEN"] = "1"
    env["VLLM_MARLIN_USE_ATOMIC_ADD"] = "1"
    env["RAY_memory_monitor_refresh_ms"] = "0"
    env["OMP_NUM_THREADS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Qwen3-Next hybrid arch only accepts FLASHINFER or TRITON_ATTN in vLLM 0.19.0.
    # FlashInfer fails on Windows because its ninja JIT trips MAX_PATH (ninja
    # binary doesn't honor LongPathsEnabled). Use TRITON_ATTN which has no JIT.
    env["VLLM_ATTENTION_BACKEND"] = "TRITON_ATTN"
    # Windows Gloo stability (inherited from vllm-windows findings):
    env["USE_LIBUV"] = "0"
    env["TORCH_NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    env["NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["PYTHONFAULTHANDLER"] = "1"

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
        "--enable-auto-tool-choice",
        "--tool-call-parser=qwen3_coder",
        "--reasoning-parser=qwen3",
        f"--kv-cache-dtype={KV_CACHE_DTYPE}",
        f"--tensor-parallel-size={TP}",
        f"--pipeline-parallel-size={PP}",
        f"--gpu-memory-utilization={GPU_MEM_UTIL}",
        "--trust-remote-code",
        "--attention-backend=TRITON_ATTN",
        "--no-use-tqdm-on-load",
        f"--host={HOST}",
        f"--port={PORT}",
    ]
    if ENFORCE_EAGER:
        args.append("--enforce-eager")
    if not ENABLE_VISION:
        args.append('--limit-mm-per-prompt={"image":0,"video":0}')
    if _world > 1:
        args.append("--distributed-executor-backend=mp")
    if USE_MTP:
        args.append(
            f'--speculative-config={{"method":"mtp","num_speculative_tokens":{NUM_SPEC_TOKENS}}}'
        )

    print("=" * 60)
    print(f"vLLM serve: {SERVED_NAME}")
    print(f"  Model   : {MODEL_PATH}")
    print(f"  Ctx     : {CTX}  |  TP: {TP}  |  PP: {PP}")
    print(f"  KV dtype: {KV_CACHE_DTYPE}  |  MTP: {USE_MTP} (n={NUM_SPEC_TOKENS})")
    print(f"  Listen  : http://{HOST}:{PORT}")
    print("=" * 60)
    print(" ".join(args))
    print("=" * 60, flush=True)

    log_path = log_path_for(PORT)
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

"""Launch vLLM serving Qwen3.6-27B-AWQ-BF16-INT4 on 2x RTX 3090.

Windows adaptation of /home/nenad/_projects/vllm/launch-qwen3.6.sh.
Power-limited GPUs (250W each) — no sudo nvidia-smi -pl on Windows.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / "venv"
VLLM_EXE = VENV / "Scripts" / "vllm.exe"

MODEL_PATH = r"G:\_models\Qwen3.6-27B-AWQ-BF16-INT4"
SERVED_NAME = "qwen3.6-27b"
HOST = "0.0.0.0"
PORT = 5000
CTX = 48000  # Max stable: KV cache at mem_util=0.92 fits ~49,600 tokens.
TP = 1
PP = 2  # Pipeline parallel: fastest working config on Windows (~21 tok/s baseline).
GPU_MEM_UTIL = 0.92
ENABLE_SPEC = False  # Spec decode requires PP=1; not compatible with our PP=2 setup.
ENFORCE_EAGER = False  # Re-enable cudagraphs for decode speedup.


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
    _world = TP * PP
    env["CUDA_VISIBLE_DEVICES"] = "0,1" if _world > 1 else "0"
    env["VLLM_SLEEP_WHEN_IDLE"] = "1"
    env["VLLM_ENABLE_CUDAGRAPH_GC"] = "1"
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "1"
    env["RAY_memory_monitor_refresh_ms"] = "0"
    env["OMP_NUM_THREADS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["VLLM_ATTENTION_BACKEND"] = "FLASHINFER"
    env["VLLM_LOGGING_LEVEL"] = "DEBUG"
    # Disable libuv in Gloo/TCPStore: libuv transport crashes on Windows
    # in c10d allreduce. Must be set before torch imports in subprocess.
    env["USE_LIBUV"] = "0"
    # Disable async-error-handling watchdog thread — it installs
    # PythonOnCompletionHook which crashes (0xC0000005) inside Gloo allreduce
    # on Windows. Safe: we don't rely on async collective timeout handling.
    env["TORCH_NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["NCCL_ASYNC_ERROR_HANDLING"] = "0"
    env["PYTHONFAULTHANDLER"] = "1"
    env["TORCH_SHOW_CPP_STACKTRACES"] = "1"
    # On Windows vLLM uses multiprocessing executor (not Ray) for TP on a
    # single node. Keep NCCL env vars out — Windows builds don't use NCCL.

    args = [
        str(VLLM_EXE), "serve", MODEL_PATH,
        f"--served-model-name={SERVED_NAME}",
        "--quantization=compressed-tensors",
        f"--max-model-len={CTX}",
        "--max-num-seqs=1",
        "--max-num-batched-tokens=4096",
        "--block-size=32",
        "--enable-prefix-caching",
        "--enable-auto-tool-choice",
        "--tool-call-parser=qwen3_coder",
        "--reasoning-parser=qwen3",
        f"--tensor-parallel-size={TP}",
        f"--pipeline-parallel-size={PP}",
        f"--gpu-memory-utilization={GPU_MEM_UTIL}",
        "--no-use-tqdm-on-load",
        f"--host={HOST}",
        f"--port={PORT}",
    ]
    if ENFORCE_EAGER:
        args.append("--enforce-eager")
    # Qwen3.6 is a VLM; disable multimodal to skip vision-encoder TP allreduce
    # profiling (crashes in c10d Gloo allreduce on Windows). Text-only use.
    args.append('--limit-mm-per-prompt={"image":0,"video":0}')
    # Multiproc executor for PP — still uses Gloo send/recv but not allreduce.
    if _world > 1:
        args.append("--distributed-executor-backend=mp")
    if ENABLE_SPEC:
        args.append('--speculative-config={"method":"mtp","num_speculative_tokens":4}')

    print("=" * 56)
    print(f"vLLM serve: {SERVED_NAME}")
    print(f"  Model : {MODEL_PATH}")
    print(f"  Ctx   : {CTX}  |  TP: {TP}  |  PP: {PP}  |  GPUs: 0,1 (250W each)")
    print(f"  Listen: http://{HOST}:{PORT}")
    print("=" * 56)
    print(" ".join(args))
    print("=" * 56, flush=True)

    log_path = HERE / "vllm_server.log"
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)
    print(f"[launcher] tee stdout -> {log_path}")
    proc = subprocess.Popen(
        args, env=env, cwd=str(VENV),
        stdout=log_f, stderr=subprocess.STDOUT, bufsize=1,
    )

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

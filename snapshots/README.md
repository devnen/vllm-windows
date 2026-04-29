# Snapshots

Each `start_*.py` is a frozen, validated config — one knob set, one set of
measured numbers. Each `start_*.bat` is a one-line wrapper that resolves
the venv via `%VLLM_WINDOWS_VENV%` and launches the corresponding `.py`.

## When to use which

| Snapshot | Decode tok/s | Ctx | When |
|---|---|---|---|
| `start_speed`     | **64.5** (long prompt) | 90 k  | Default for daily use. MTP n=6, GPU1, 350 W. |
| `start_127k`      | 53.4                   | 127 k | When you need the largest single-GPU ctx. MTP n=3. |
| `start_mtp4`      | 58.3                   | 120 k | Mid-balance speed vs ctx. |
| `start_72tps`     | ~72 short prompts      | 32 k  | Original short-prompt baseline. |
| `start_pp2_160k`  | 43.5                   | 160 k | Both GPUs, no MTP. Use only when 127 k isn't enough. |
| `start_gpu0_50k`  | volatile               | ~9–50 k | Single-GPU users with the display attached. Read [`docs/HARDWARE.md`](../docs/HARDWARE.md). |

## How they resolve paths

Every snapshot imports from `_common.py`:

```python
from _common import VENV, VLLM_EXE, MODEL_PATH, VCVARS, log_path_for
```

`_common.py` reads four env vars with sensible defaults:

| Variable | Default |
|---|---|
| `VLLM_WINDOWS_VENV`   | `<repo>\venv` |
| `VLLM_MODEL_DIR`      | `<repo>\models\Qwen3.6-27B-int4-AutoRound` |
| `VLLM_WINDOWS_VCVARS` | First found among VS 2022 Community / Pro / Enterprise / BuildTools |
| `VLLM_WINDOWS_LOGS`   | `<repo>\logs` |

So a typical install just sets `VLLM_MODEL_DIR` once (or drops the model
into the default location) and everything else resolves automatically.

## Adding your own

1. Copy `start_speed.py` → `start_<myname>.py`.
2. Edit only the constants block (CTX, TP, PP, MTP_N, GPU_MEM_UTIL, etc.).
3. Copy `start_speed.bat` → `start_<myname>.bat`, change the `.py` filename.
4. Add a card under `windows.configs[]` in `launcher\configs.yaml`.
5. Bench, validate coherence, commit.

Try not to parameterise via env vars within a snapshot — the whole point
is that each snapshot is self-describing and rollback-able. A new config
is a new file.

## Running outside the launcher

Every `.bat` is double-clickable. From cmd:

```cmd
set VLLM_MODEL_DIR=G:\_models\Qwen3.6-27B-int4-AutoRound
snapshots\start_speed.bat
```

To stop all servers:

```cmd
snapshots\stop_vllm.bat
```

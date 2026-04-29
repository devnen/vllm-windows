# Changes vs SystemPanic/vllm-windows

This fork (`devnen/vllm-windows`) sits 6 commits ahead of `SystemPanic/vllm-windows`
at merge-base `76aefe152` ("Merge branch 'vllm-project:main' into main"). Every
change below was developed and validated on a local Windows 10 box with 2× RTX 3090.

The upstream tracking remote in this clone is named `upstream`; `origin` points to
`devnen/vllm-windows`.

```
upstream  https://github.com/SystemPanic/vllm-windows.git
origin    https://github.com/devnen/vllm-windows.git
```

## Diff summary

```
 .gitignore                                  |    6 +
 bench_popos.py                              |  106 ++
 qwen3.6-27b.bat                             |   25 +
 start.bat                                   |   41 +
 start_qwen.py                               |  136 ++
 test_qwen.py                                |  104 ++
 vllm/entrypoints/openai/models/serving.py   |   11 +
 vllm/reasoning/qwen3_reasoning_parser.py    |  108 +-
 windows_patches/README.md                   |   93 ++
 windows_patches/base_device_communicator.py |  402 +++
 windows_patches/cuda_communicator.py        |  494 +++
 windows_patches/gpu_worker.py               | 1059 +++
 windows_patches/parallel_state.py           | 2176 +++
 windows_patches/qwen3_reasoning_parser.py   |  231 +
 windows_patches/serving_models.py           |  340 +
 15 files changed, 5320 insertions(+), 12 deletions(-)
```

## Commits ahead of SystemPanic (oldest → newest)

### 1. `abc2480f8` — Add start.bat launcher and .gitignore for local Windows install

Local-install scaffolding: top-level `start.bat` and a `.gitignore` to keep
the venv, model snapshots, and bench artifacts out of git. No vLLM source
changes.

### 2. `f23a2a977` — PP=2 TP=1 launcher + streaming test; progress to warmup, request dispatch blocked

First Windows multi-GPU launcher. Adds:
- `start_qwen.py` — Python launcher targeting Qwen3.6-27B with PP=2, TP=1.
- `qwen3.6-27b.bat` — wrapper for the launcher.
- `test_qwen.py` — streaming client used to drive the server while iterating on patches.

Engine boots through worker warmup but request dispatch was still blocked at this
point — the fix lands two commits later.

### 3. `c90698be3` — Windows CPU-relay for Gloo allreduce/broadcast/send/recv (enables TP=2)

The flagship Windows-enablement patch. Gloo (the only collective backend torch
ships on Windows because there is no NCCL) hangs on CUDA tensors during
collective ops. This commit extends the existing PP-side CPU-relay pattern
(`isend_tensor_dict` / `irecv_tensor_dict` in `parallel_state.py`) to the
TP-side collectives:

- `vllm/distributed/device_communicators/cuda_communicator.py` — CPU-relay for
  `all_reduce`, `broadcast`, `send`, `recv`. Adds `_fallback_all_reduce`.
- `vllm/distributed/device_communicators/base_device_communicator.py` — same
  pattern for the base class fallbacks (`all_reduce`, `all_gather`, `broadcast`).

Each path stages CUDA tensors through pinned CPU buffers on the cpu_group when
`os.name == "nt"`, then copies the result back. Patched copies are mirrored into
`windows_patches/` for recovery after a venv rebuild.

`start_qwen.py` configuration updates that landed with this commit:
- `CTX=48000` (6× prior) with `gpu-memory-utilization=0.92` (~49.6k KV tokens).
- `enforce_eager=False` — cudagraphs re-enabled, ~27 tok/s at 32k ctx.
- Speculative decoding stays off (PP not supported for Qwen3.6-MTP on 0.19.0).

**Performance reality:** TP=2 PP=1 boots correctly but runs at ~7.5 tok/s
because allreduce fires at every transformer layer and CPU-relay dominates.
PP=2 remains the throughput-optimal multi-GPU config (~21+ tok/s, since only
one hidden-state hand-off per layer crosses CPU).

### 4. `ca89aab67` — Add bench_popos.py: streaming tok/s benchmark client for popos vLLM server

Standalone benchmark client (not a vLLM source change). Streams completions
from the popos Linux box at `192.168.1.116` and reports prefill / decode
tok/s. Mirrors the local-Windows bench harness so cross-OS numbers stay
comparable.

### 5. `6cb754325` — Qwen3 reasoning parser: treat `<tool_call>` as implicit `</think>` (PR #35687 mirror)

Verbatim mirror of upstream vLLM PR #35687. Qwen3.5/3.6 sometimes emits
`<tool_call>` inside a `<think>` block without first closing `</think>`.
Without this patch the entire output gets classified as reasoning, the
`qwen3_coder` tool parser receives empty content, and the tool call is
silently dropped.

Changes in `vllm/reasoning/qwen3_reasoning_parser.py`:
- `__init__` records `<tool_call>` / `</tool_call>` token ids.
- New overrides: `is_reasoning_end`, `is_reasoning_end_streaming`,
  `extract_content_ids` — same shape as `KimiK2ReasoningParser`.
- `extract_reasoning` falls back to `<tool_call>` as an implicit reasoning
  end when `</think>` is absent.
- Streaming variant mirrors the same 3-way branch.
- Pair-checks `<tool_call>` vs `</tool_call>` so chat-template examples
  embedded in prompts cannot false-fire.

Mirrored to `windows_patches/qwen3_reasoning_parser.py`.

### 6. `978b9752f` — Add VLLM_ACCEPT_ANY_MODEL_NAME env var for single-tenant deploys

When `VLLM_ACCEPT_ANY_MODEL_NAME` is truthy (1/true/yes/on),
`OpenAIModelRegistry.is_base_model` returns `True` for any model name, so the
OpenAI-compatible server accepts arbitrary values of the request `model` field
and resolves them to the first served base model.

- `vllm/entrypoints/openai/models/serving.py` — adds the env-gated short circuit.
- `windows_patches/serving_models.py` + `windows_patches/README.md` updated.

LoRA path is unaffected because `_check_model` consults the `lora_requests`
dict before falling through to `is_base_model`. Default off — upstream
behavior unchanged when the env var is unset.

## File-by-file inventory (vs SystemPanic merge-base)

| Path | Type | Origin commit |
|---|---|---|
| `.gitignore` | added | abc2480f8 |
| `start.bat` | added | abc2480f8 |
| `start_qwen.py` | added | f23a2a977 (config tuned in c90698be3) |
| `qwen3.6-27b.bat` | added | f23a2a977 |
| `test_qwen.py` | added | f23a2a977 |
| `bench_popos.py` | added | ca89aab67 |
| `vllm/distributed/device_communicators/cuda_communicator.py` | modified (TP CPU-relay) | c90698be3 |
| `vllm/distributed/device_communicators/base_device_communicator.py` | modified (TP CPU-relay) | c90698be3 |
| `vllm/reasoning/qwen3_reasoning_parser.py` | modified (`<tool_call>` as reasoning end) | 6cb754325 |
| `vllm/entrypoints/openai/models/serving.py` | modified (`VLLM_ACCEPT_ANY_MODEL_NAME`) | 978b9752f |
| `windows_patches/README.md` | added | abc2480f8, expanded each commit |
| `windows_patches/parallel_state.py` | added (PP CPU-relay copy) | f23a2a977 era |
| `windows_patches/cuda_communicator.py` | added (TP CPU-relay copy) | c90698be3 |
| `windows_patches/base_device_communicator.py` | added (TP CPU-relay copy) | c90698be3 |
| `windows_patches/gpu_worker.py` | added (worker patch copy) | f23a2a977 era |
| `windows_patches/qwen3_reasoning_parser.py` | added (parser patch copy) | 6cb754325 |
| `windows_patches/serving_models.py` | added (env-gated registry copy) | 978b9752f |

## Categories

**Source patches in `vllm/`:**
1. **Distributed CPU-relay (Windows-enablement, mandatory for TP/PP > 1)** —
   `cuda_communicator.py`, `base_device_communicator.py`. Earlier
   PP-side relay in `parallel_state.py` came from SystemPanic + the prior
   session and is mirrored in `windows_patches/parallel_state.py`.
2. **Reasoning-parser correctness (Qwen3.5/3.6 tool calls)** —
   `qwen3_reasoning_parser.py`. Mirror of upstream PR #35687.
3. **OpenAI server ergonomics (single-tenant)** —
   `entrypoints/openai/models/serving.py`. Env-gated; off by default.

**Local launchers / scripts (not part of vLLM proper):**
- `start.bat`, `start_qwen.py`, `qwen3.6-27b.bat`, `test_qwen.py`, `bench_popos.py`.

**Patch backups (`windows_patches/`):**
- Mirrors every venv file the patches touch, plus a README that maps each
  source file to where it has to be copied after a venv rebuild. This is the
  recovery path called out in the project skill.

## Reapplying after a venv rebuild

```bash
cp windows_patches/parallel_state.py            <venv>/Lib/site-packages/vllm/distributed/parallel_state.py
cp windows_patches/cuda_communicator.py         <venv>/Lib/site-packages/vllm/distributed/device_communicators/cuda_communicator.py
cp windows_patches/base_device_communicator.py  <venv>/Lib/site-packages/vllm/distributed/device_communicators/base_device_communicator.py
cp windows_patches/gpu_worker.py                <venv>/Lib/site-packages/vllm/v1/worker/gpu_worker.py
cp windows_patches/qwen3_reasoning_parser.py    <venv>/Lib/site-packages/vllm/reasoning/qwen3_reasoning_parser.py
cp windows_patches/serving_models.py            <venv>/Lib/site-packages/vllm/entrypoints/openai/models/serving.py
```

Exact destinations are also documented in `windows_patches/README.md`.

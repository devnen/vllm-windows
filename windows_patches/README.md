# Windows patches for vLLM 0.19

Backup copies of vLLM files patched to work on Windows with Gloo
backend (no NCCL). These files live in
`venv/Lib/site-packages/vllm/...` in the active installation — this
folder preserves a copy so the patches survive venv reinstall.

## Root cause

On Windows, PyTorch ships only the Gloo distributed backend for NVIDIA
GPUs (no NCCL). Gloo cannot directly send/recv/allreduce CUDA tensors;
attempts hang in `irecv` or crash at `0xC0000005` in
`PythonOnCompletionHook` inside `allreduce`.

## Fix strategy

Stage CUDA tensors through CPU buffers on the CPU (Gloo) process group
when `os.name == "nt"`. Applied in:

### `parallel_state.py`

- `isend_tensor_dict` and `irecv_tensor_dict`: CPU-relay for CUDA
  tensors crossing a PP boundary. Without this, PP workers hang on
  `irecv` of hidden-state / residual tensors.

### `device_communicators/cuda_communicator.py`

- `_fallback_all_reduce` (new helper): CPU-relay when pynccl is
  unavailable (always, on Windows).
- `all_reduce`: routes through fallback.
- `broadcast`: CPU-relay instead of raising.
- `send` / `recv`: CPU-relay.

### `device_communicators/base_device_communicator.py`

- `all_reduce`, `all_gather`, `broadcast`: CPU-relay fallbacks for the
  same reason.

### `v1/worker/gpu_worker.py`

- Carries over from prior session; no Windows-specific logic beyond
  `AsyncIntermediateTensors.wait_for_comm`.

### `reasoning/qwen3_reasoning_parser.py` (PR #35687 mirror)

Qwen3.5/3.6 models sometimes emit `<tool_call>` inside a `<think>` block
without closing `</think>` first. The 0.19.0 wheel's parser swallows the
entire output as reasoning, the `qwen3_coder` tool parser sees empty
content, and the tool call is silently dropped.

This file is a verbatim mirror of vLLM main's parser (PR #35687):
adds `_tool_call_token_id` init, three new override methods
(`is_reasoning_end`, `is_reasoning_end_streaming`, `extract_content_ids`),
and an implicit-end branch in both `extract_reasoning` and
`extract_reasoning_streaming`. Pair-checks `<tool_call>` vs
`</tool_call>` so chat-template examples in prompts don't false-fire.

### `entrypoints/openai/models/serving.py` (opt-in wildcard model name)

Adds `VLLM_ACCEPT_ANY_MODEL_NAME` env var (default off). When set to
`1`/`true`/`yes`/`on`, `OpenAIModelRegistry.is_base_model` returns True
for any model name, so the OpenAI server resolves any client-provided
`"model"` field to the first served base model. Useful for single-tenant
single-model setups where keeping client configs in sync with
`--served-model-name` is friction. LoRA path is unaffected (`_check_model`
checks the lora dict before falling through to `is_base_model`).

## Applying to a fresh venv

After a clean install of vLLM 0.19, copy these files over the installed
versions:

```
cp windows_patches/parallel_state.py              venv/Lib/site-packages/vllm/distributed/parallel_state.py
cp windows_patches/cuda_communicator.py           venv/Lib/site-packages/vllm/distributed/device_communicators/cuda_communicator.py
cp windows_patches/base_device_communicator.py    venv/Lib/site-packages/vllm/distributed/device_communicators/base_device_communicator.py
cp windows_patches/gpu_worker.py                  venv/Lib/site-packages/vllm/v1/worker/gpu_worker.py
cp windows_patches/qwen3_reasoning_parser.py      venv/Lib/site-packages/vllm/reasoning/qwen3_reasoning_parser.py
cp windows_patches/serving_models.py              venv/Lib/site-packages/vllm/entrypoints/openai/models/serving.py
```

## Verified configurations (2x RTX 3090, 250W limit, Qwen3.6-27B-AWQ)

| Config                                           | tok/s  | Notes                          |
|--------------------------------------------------|--------|--------------------------------|
| PP=2 TP=1, ctx=8k, enforce_eager                 | ~21    | Initial working baseline        |
| PP=2 TP=1, ctx=32k, cudagraphs                   | ~26.7  | Best throughput                 |
| PP=2 TP=1, ctx=48k, cudagraphs, mem_util=0.92    | ~23    | Max stable context              |
| TP=2 PP=1, ctx=8k, enforce_eager                 | ~7.5   | Works but CPU-relay bottleneck  |

Speculative decoding (`method=mtp`) is **not compatible with PP** for
this model (raises `NotImplementedError: Pipeline parallelism is not
supported for this model`). Stays off.

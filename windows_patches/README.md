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

### `tool_parsers/qwen3coder_tool_parser.py`, `tool_parsers/qwen3xml_tool_parser.py`, `tool_parsers/utils.py`, `tool_parsers/abstract_tool_parser.py` (PR #40861 mirror)

Backport of [vllm-project/vllm#40861](https://github.com/vllm-project/vllm/pull/40861)
("Bugfix: Fix Qwen3 XML and Coder streaming tool call parser
regressions"). Open upstream as of this writing — vendored here against
the recurring tool-call failures the OP catalogues.

What it fixes:

- **`Qwen3CoderToolParser` streaming**:
  - Split `<tool_call>` tag detection — when the tag fragments across
    two deltas (e.g. `<tool_` then `call>`), the prior parser dropped the
    call silently.
  - Header-vs-params split: when `<tool_call><function=name>` arrives in
    delta 1 and the params + `</function>` arrive in delta 2, parameters
    were dropped.
  - Last content message not flushed after all tool calls completed.
  - Structural delimiters (`</tool_call>`, `</function>`, `</parameter>`)
    appearing as **literal text** inside a parameter value (e.g. when the
    user asks the model to write code or documentation that contains those
    strings) were treated as closing delimiters, truncating or corrupting
    the value.
- **`Qwen3XMLToolParser` streaming**:
  - Delayed text emission between consecutive tool calls.
  - `anyOf` schema-type detection: nullable schemas
    (`{"anyOf": [{"type":"string"}, {"type":"null"}]}`) were classified as
    `"object"`, triggering `json.loads` and crashing on plain strings.
  - Double-close fallback when `</parameter>` appeared inside a value.
- **Both parsers**: speculative decoding could deliver several complete
  tool calls in a single delta; only the first was emitted.
- **Local fix on top of PR #40861 (parallel-call streaming leak)**: when
  3+ parallel `<tool_call>` blocks were emitted in one assistant turn,
  the trailing-free-text emission at the end of
  `extract_tool_calls_streaming` (added by PR #40861 to flush content
  that follows the last `</tool_call>` in MTP / spec-decode bursts)
  also matched the *opener* of the next tool call sitting in
  `current_text`, leaking that next call's raw XML
  (`<tool_call><function=...><parameter=...>...</tool_call>`) into the
  `delta.content` stream while ALSO emitting the same call structurally
  via `delta.tool_calls`. Chat clients then rendered the leaked XML as
  plain text in the conversation. Fixed by clipping the trailing region
  at the next `<tool_call>` opener (or its partial-tag overlap) before
  emitting. Regression test: `test_toolcall.py::t9_parallel_streaming_leak`.

The two parser files are wholesale replacements (head of the upstream PR
branch `ExtReMLapin/vllm@qwen3_combined_fixes`) plus the parallel-call
trailing-text fix above. `utils.py` adds two
helpers (`partial_tag_overlap`, `find_tool_properties`); the rest of the
file is unchanged. `abstract_tool_parser.py` adds a
`supports_required_and_named` class attribute and tightens the
Pydantic v2 construction of `ResponseTextConfig` so that nested tool
config isn't silently dropped from `model_dump`.

End-to-end verification lives at
`C:\_projects\vllm-turbo\test_toolcall.py` (9 tests covering simple
calls, special characters in args, CoT leakage, multi-turn, streaming
parity, structural-delimiter literals in values, parallel calls, a
5-round agentic chain, and the 3-call streaming-leak regression). All
9 pass on the patched fork.

### `templates/qwen3.5-enhanced.jinja`

Vendored at the repo root under `templates/`, not under
`windows_patches/` because it is a *template asset*, not a source
overlay. M2.5-style interleaved-thinking chat template — closes
`</thinking>` properly before tool calls and treats any unclosed
`<thinking>` block in history as plain content, not reasoning content.
Required by the canonical Qwen 3.6 agentic recipe (paired with
`--tool-call-parser=qwen3_coder` and
`--default-chat-template-kwargs='{"preserve_thinking": false}'`).
Source: [`allanchan339/vLLM-Qwen3.5-27B`](https://github.com/allanchan339/vLLM-Qwen3.5-27B).

### `entrypoints/openai/models/serving.py` (always-accept any model name)

`OpenAIModelRegistry.is_base_model` is hardwired to return `True`,
unconditionally. The OpenAI-compatible server resolves any client-provided
`"model"` field to the first served base model, so clients no longer need
to match `--served-model-name` exactly. This is a deliberate fork
deviation: the vllm-windows install is single-tenant, single-model, and
keeping client configs in sync with the served name was friction with no
upside. LoRA path is unaffected — `_check_model` consults the lora_requests
dict before falling through to `is_base_model`.

Earlier revision of this fork (commit 978b9752f) gated the behavior behind
`VLLM_ACCEPT_ANY_MODEL_NAME`. That env var is no longer read; the wildcard
is always on.

## Applying to a fresh venv

After a clean install of vLLM 0.19, copy these files over the installed
versions:

```
cp windows_patches/parallel_state.py              venv/Lib/site-packages/vllm/distributed/parallel_state.py
cp windows_patches/cuda_communicator.py           venv/Lib/site-packages/vllm/distributed/device_communicators/cuda_communicator.py
cp windows_patches/base_device_communicator.py    venv/Lib/site-packages/vllm/distributed/device_communicators/base_device_communicator.py
cp windows_patches/gpu_worker.py                  venv/Lib/site-packages/vllm/v1/worker/gpu_worker.py
cp windows_patches/qwen3_reasoning_parser.py      venv/Lib/site-packages/vllm/reasoning/qwen3_reasoning_parser.py
cp windows_patches/qwen3coder_tool_parser.py      venv/Lib/site-packages/vllm/tool_parsers/qwen3coder_tool_parser.py
cp windows_patches/qwen3xml_tool_parser.py        venv/Lib/site-packages/vllm/tool_parsers/qwen3xml_tool_parser.py
cp windows_patches/tool_parsers_utils.py          venv/Lib/site-packages/vllm/tool_parsers/utils.py
cp windows_patches/abstract_tool_parser.py        venv/Lib/site-packages/vllm/tool_parsers/abstract_tool_parser.py
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

# Speculative-decoding × parallelism matrix

What works on the SystemPanic 0.19.0 wheel + the devnen patches.

| Combo | Result |
|---|---|
| TP=1 + MTP (n=3..6) | **Works.** 53–72 tok/s on Qwen3.6-27B INT4 depending on N and prompt class. The headline `start_speed` config. |
| TP=1 + draft-model | Works *if* vocab matches target. Qwen3.6-27B vocab=248320; no small (≤2 B) Qwen3.5/3.6 drafter exists with that vocab. Qwen3-0.6B has vocab=151936 and fails at boot with pydantic `ValidationError`. Opt-in shell `start_draft.py` is reserved for when a vocab-matched drafter ships. |
| PP=2 + MTP | `NotImplementedError: Pipeline parallelism is not supported for this model` on Qwen3-Next at engine init. Documented in vLLM upstream — no workaround on 0.19.0. |
| PP=2 + ngram | `RuntimeError: 'GPUModelRunner' object has no attribute 'drafter'` at worker rank during `determine_available_memory`. vLLM 0.19.0 bug. |
| PP=2 + draft-model | Unsupported since vLLM 0.15 (hard block in upstream). |
| **PP=2, no spec-decode** | **Works.** 43.5 tok/s, ctx up to 160 k. The `start_pp2_160k` config — use only when 127 k of single-GPU context isn't enough. |
| TP=2 + MTP | Works after the CPU-relay patch but ~7.5 tok/s — the CPU-relay allreduce dominates per-layer cost. **Don't.** |
| TP=2 + ngram / draft | Same — TP=2 itself is the wrong config on Windows. |

**Bottom line:** pick **either** speed (MTP on a single GPU) **or**
context (PP=2 across both GPUs with no spec-decode). You cannot have both
on this wheel.

If MTP+PP support lands in a future 0.19.x release that SystemPanic ships
a wheel for, this matrix changes. We'll re-bench when that happens.

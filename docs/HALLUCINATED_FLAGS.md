# Flags you'll see online that don't exist here

The vLLM ecosystem moves fast and search engines + Reddit posts + ppx-cli
output happily reference flags from later releases, niche forks, or pure
hallucination. **Before trying any "creative" flag from a web answer,
verify it actually exists on this wheel.**

How to verify env vars:

```powershell
.\venv\Scripts\python.exe -c "from vllm import envs; import sys; sys.stdout.write('\n'.join(sorted(k for k in dir(envs) if k.startswith('VLLM_'))))"
```

How to verify CLI flags:

```powershell
.\venv\Scripts\vllm.exe serve --help | Select-String <fragment>
```

## Confirmed-fictional / wrong-version on the 0.19.0 wheel

| Flag / env var | What you'll find online | Reality on this wheel |
|---|---|---|
| `VLLM_FLASHINFER_FORCE_TENSOR_CORES` | "set this for free perf" | Does not exist. |
| `VLLM_USE_FLASH_ATTN_3` | "FA3 is way faster on Hopper+" | Does not exist on 0.19.0. |
| `--decode-threshold` | "tune speculative threshold" | Does not exist. |
| `--scheduler-delay-mult` | "for streaming throughput" | Does not exist. |
| `--cuda-graph-sizes` | Used in copy-paste recipes | Wrong name. The flag is `--cudagraph-capture-sizes` (no hyphen between cuda and graph). |
| `--kv-cache-dtype=int8` | Suggested by ppx | Not accepted. TRITON_ATTN takes only `auto` (BF16), `fp8`, `fp8_e4m3`. |
| `--kv-cache-dtype=NVFP4` / `MXFP4` | Late-2025 vLLM features | Not in 0.19.0. |
| `--kv-cache-dtype=turboquant_3bit_nc` | Genesis patches blog posts | Not in 0.19.0; needs the Genesis tree which hasn't been Windows-ported. |
| `--kv-cache-dtype=fp8_e5m2` | Linux recipes from r/LocalLLaMA | Rejected by TRITON_ATTN with `only accepts {"fp8","fp8_e4m3"}`. Use `fp8_e4m3`. |
| `VLLM_ATTENTION_BACKEND` env var | "set this and you're done" | The env var is *ignored* on 0.19.0. Pass `--attention-backend=TRITON_ATTN` as a CLI arg instead. (Set the env var too if you like — only the CLI matters.) |
| `--enable-turboquant` | Turbo project flags | Not in this wheel. |
| `--cpu-offload-gb` | "for big models" | Exists but extends *batch capacity*, not *per-sequence ctx*. With `max-num-seqs=1` it does nothing useful. |
| `--swap-space` | Same | Same — batch capacity, not ctx. |

## Anti-levers — exist but measured to be no-ops or worse on this wheel

| Lever | Web claim | Measured on this wheel |
|---|---|---|
| `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` | Saves fragmentation | KV stayed at 4.74 GiB / ctx ceiling 121 600 with and without. Harmless; not worth setting. |
| `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1` | Linux setting `=0` saved +4.7 % ctx | On this Windows wheel `=1` measured slightly *worse* (KV 4.74 → 4.67 GiB). Default is fine. |
| `--num-gpu-blocks-override` higher than auto-profile | "force more KV" | Guaranteed OOM at first request. Don't. |
| `--cudagraph-capture-sizes 1 2 4 8` | "free up KV" | No effect with `max-num-seqs=1`; engine already infers a minimal capture set. |
| `--max-num-batched-tokens=8192` | "bigger batches" | Shrinks KV pool from 4.74 → 2.64 GiB on this wheel. The MNBT optimum is non-monotonic; 4128 is the measured peak. |

## Where the bad info comes from

- **Perplexity / ppx-cli answers about vLLM** are heavily hallucinated.
  Treat them as "list of candidate flags to grep against the live binary",
  not as authoritative.
- **Reddit recipes** often pin a nightly vLLM version that has flags 0.19.0
  doesn't. Always check which version a recipe was tested on.
- **Linux-only patches** (Genesis, TurboQuant, DFlash drafter) get
  cross-posted with no caveat. Strip them out before trying anything from
  the post.
- **`vllm/envs.py` was renamed across versions.** Some attribute names that
  existed in 0.18 don't in 0.19, and vice versa. Always inspect the live
  module on your install.

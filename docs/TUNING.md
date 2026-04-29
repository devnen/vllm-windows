# Tuning — the levers that actually move the numbers

The lever set on this wheel is narrower than upstream-Linux because TurboQuant
KV, FlashInfer, and a few Genesis patches are unavailable. What remains:

## Decode TPS

1. **MTP num_speculative_tokens.** The Reddit "n=3 is the sweet spot"
   conventional wisdom is for *short prompts*. On long-prompt dense code
   (24 k tokens of Python source, our bench harness) the acceptance curve
   shifts later:
   ```
   n=3 / 4 / 5 / 6 / 7 / 8  →  53.4 / 58.3 / 62.8 / 64.5 / 61.5 / 58.0 tok/s
   ```
   **n=6 is the long-prompt peak**, dropping a cliff at n=7. Always re-sweep
   on a representative prompt for a new workload — don't trust a single
   fixed number.

2. **Power cap.** 250 W → 350 W: prefill +16 %, decode unchanged (decode
   is memory-bandwidth-bound at batch=1 / max-num-seqs=1). If you want
   decode speed, more power doesn't help; if you want short-prompt TTFT,
   it does.

3. **Bigger ctx slows decode at fixed MTP.** Measured at MTP n=6:
   ctx=90 k → 64.5, ctx=112 k → 60.4 (–6 %). Likely KV-pool memory
   bandwidth during attention. If a snapshot doesn't need the full ctx
   headroom, don't pay for it — split into a "speed" snapshot (smaller
   ctx) and a "max-ctx" snapshot. We have both.

4. **Cudagraphs on.** `--enforce-eager` costs ~55 % on Linux; untested on
   Windows but almost certainly similar. Don't disable.

5. **Attention backend.** `TRITON_ATTN` only — FlashInfer JIT is broken
   on Windows because ninja trips MAX_PATH inside flashinfer cache dirs.
   Pass `--attention-backend=TRITON_ATTN` as a CLI flag (the env var alone
   is ignored on 0.19.0).

6. **Small-boost env vars** (no downside):
   ```
   VLLM_USE_FLASHINFER_SAMPLER=1
   VLLM_ENABLE_CUDAGRAPH_GC=1
   VLLM_MARLIN_USE_ATOMIC_ADD=1
   ```

## Prefill TPS

1. **`--max-num-batched-tokens` peak is around 4128, non-monotonic.** Lowering
   to 2048 *shrinks* the available KV from 4.74 GiB → 2.99 GiB; raising to
   8192 shrinks it to 2.64 GiB. Leave at 4128. (The chunked-prefill scratch
   buffer scales weirdly with this number on this wheel.)

2. `--enable-chunked-prefill` and `--enable-prefix-caching` are on in every
   shipped snapshot.

## Context

1. **Just raise `--max-model-len`.** On a fresh `start_72tps` snapshot the
   KV pool already holds ~75 k tokens of physical KV but `--max-model-len=32000`
   caps it at 32 k. Bumping to 121 k costs nothing (measured: prefill 845 vs
   835 tok/s, decode within noise on a 24 k-token bench prompt). The 32 k
   conservatism is a copy-from-Linux artifact, not a hardware limit.

2. **GPU1 mem-util ceiling is 0.948** (display-free). When GPU0 is idle,
   vLLM sees free=22.76/24 GiB on GPU1 *after* CUDA context init reserves
   ~1.5 GiB. 0.948 passes; 0.95 trips by ~40 MiB. The 0.92 → 0.94 → 0.948
   progression: each step adds ~0.2 GiB KV / ~6.4 k tokens of ctx ceiling.
   GPU0 with display: stay at 0.92 max.

3. **Use vLLM's auto-profiler as a context oracle.** Set
   `--max-model-len=200000` (deliberately too high) and read the engine's
   ```
   ValueError: ... estimated maximum model length is N
   ```
   line. That's the exact ceiling for the current config. Push max-model-len
   to ~99 % of N. Wrapped as a tool: `python windows_tools\probe_max_ctx.py`.

4. **PP=2** when you need >121 k. ~2× the KV pool but kills MTP, capping
   decode at ~43 tok/s. Use [`start_pp2_160k`](../snapshots/start_pp2_160k.bat)
   for this case only.

5. `--kv-cache-dtype=fp8_e4m3` always. fp8_e5m2 is rejected by TRITON_ATTN.

6. `--max-num-seqs=1` always — single-user only.

## Reading the KV pool from logs

After a successful boot, two lines in `logs\vllm_server.<port>.log` matter:

```
INFO ... [kv_cache_utils.py:1319] GPU KV cache size: N tokens
INFO ... [kv_cache_utils.py:1324] Maximum concurrency for X tokens per request: Y.YYx
```

The "concurrency" factor is the real pool size: `physical_pool ≈ X × Y`.
The "GPU KV cache size: N tokens" line is *not* the pool size on this
wheel — it's a derived ceiling. Trust the `Maximum concurrency` line.

When ctx is too high you instead get the `estimated maximum model length`
error described above — read it, set max-model-len just under, re-launch.

## Sweeping your own configs

`windows_tools\bench_summarize.py` runs a 24 k-token Python source-summary
prompt against any port and appends one TSV row per run to `runs.tsv`.
Schema:

```
label  kv_pool_GiB  ctx  mtp_n  prefill_tok_s  decode_tok_s  ttft_s  wall_tok_s  prompt_tokens  completion_tokens  notes
```

Convention: cold rows labeled `<config>`, warm rerun rows `<config>_run2`,
`<config>_run3`. Cold runs hit fresh prefix cache (TTFT ~25 s on 24 k-token
prompts); warm runs report TTFT ~4 s / prefill ~5 900 tok/s — that warm
prefill is *bogus* for cross-config comparison. Decode TPS *is* meaningful
on warm runs and useful for run-to-run noise.

`windows_tools\tune_restart.py --port 5001` kills any orphan EngineCore /
APIServer / ZMQ listener tied to that port (regex-parsing the log) and
relaunches the snapshot. Use this between sweeps so port 5001 isn't
held by yesterday's process.

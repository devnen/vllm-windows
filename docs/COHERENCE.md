# Coherence — TPS without it is a lie

A wrong KV-dtype, wrong quantization flag, or a corrupted shard will let
vLLM cheerfully report 60+ tok/s while emitting `* * * *` or
`the the the the`. The number is right; the output is garbage. **Always
validate coherence before you trust a TPS number** — yours, ours, or
anyone's.

## The 3-tier validator

Run [`windows_tools/check_coherence.py`](../windows_tools/check_coherence.py)
against any running server:

```powershell
python windows_tools\check_coherence.py --port 5001
```

Three prompts get sent at three different generation lengths:

1. **Capital of France** (200 tok) — sanity. Expect one short sentence
   ending with `Paris.` and `finish_reason=stop`.
2. **300-word Whiskers cat / rooftop garden story** (700 tok) — long-form
   narrative. Tests whether KV cache stays coherent past a few hundred
   tokens.
3. **Iterative Fibonacci with docstring** (500 tok) — code generation.
   Different distribution than prose; catches issues that prose hides.

Exit code:
- `0` — all three coherent. Good.
- `1` — at least one degenerate. Don't ship this config.
- `2` — server unreachable. Check `--port`.

The script prints the first 200 chars of each response so you can eyeball
the output yourself.

## Degenerate-attractor patterns

These are the patterns the validator looks for. If you see any of them
in production, you have a coherence problem regardless of what TPS says:

| Pattern | What it means |
|---|---|
| `* * * * * * *` | Attention collapsed to a single high-prob token |
| `the the the the` | Same with a different collapse point |
| `a a a a a a` | Same |
| `**:**:**:**` | Delimiter loop, often after a markdown table |
| `\n\n\n\n\n\n\n` | Format-token loop |
| Coherent for 30 tokens then "the the the" mid-sentence | KV cache aged past attention-quant coherence limit |

## Causes (in rough order of likelihood)

1. **Wrong `--quantization` flag** for the model. AutoRound checkpoint
   loaded with `awq_marlin` will load fine and produce gibberish.
2. **KV-dtype too aggressive.** `fp8_e5m2` is *rejected* by TRITON_ATTN
   (only fp8 / fp8_e4m3 accepted on Windows). 3-bit / TurboQuant KV is
   not in the 0.19.0 wheel.
3. **Shard corruption.** Run
   [`windows_tools/verify_model_sha.py`](../windows_tools/verify_model_sha.py)
   to check every shard against HuggingFace's `x-linked-etag`. One bad
   shard = consistent local SHA, garbage output.
4. **`max_tokens` runs out before `</think>`** when using
   `--reasoning-parser qwen3`. The whole response ends up in the
   `reasoning` field with `content=""` — looks degenerate but is just
   truncated reasoning. Raise `max_tokens` or append `/no_think` to the
   prompt or drop the parser flag.
5. **MTP head missing from quant.** Qwen3.6-27B AutoRound from Lorbus
   keeps `mtp.fc` in BF16. Other quants either OOM allocating a fresh
   BF16 head or quantize it to INT4 and the loader silently skips it →
   0 % draft acceptance, no speedup, output usually still coherent. See
   [`MTP_HEAD.md`](MTP_HEAD.md).

## When in doubt, drop to a known-coherent baseline

A safe rollback config is:

```
TP=1, PP=1, MTP=off, --kv-cache-dtype=auto (BF16),
--enforce-eager, ctx=8000
```

This is slow but it should always be coherent on the Lorbus AutoRound
quant. If even that produces gibberish, the model file is corrupt — not
a vLLM problem.

## Spec-decode metrics in the log

When MTP is enabled, vLLM logs per-window stats:

```
Spec decode metrics: draft_acceptance_rate=0.62, system_efficiency=1.85
```

- `draft_acceptance_rate` — what fraction of the speculated tokens were
  accepted. Should be 0.4–0.7 for prose, 0.2–0.5 for dense code.
- `system_efficiency` — net throughput multiplier vs no spec-decode.
  Should be > 1.2 to be worth running.

If `system_efficiency < 1.0`, MTP is *costing* you tokens. Either drop
N or disable spec-decode entirely:

```powershell
Get-Content logs\vllm_server.5001.log -Wait | Select-String 'draft_acceptance|system_efficiency'
```

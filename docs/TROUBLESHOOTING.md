# Troubleshooting

Every failure mode we've actually hit, with the fix. Sorted roughly by
how often it bites.

| Symptom | Likely cause | Fix |
|---|---|---|
| `OSError: free memory < required` at startup despite a 24 GB card | `--gpu-memory-utilization >= 0.95` on a card with the display attached | Drop to 0.92 (or use `start_gpu0_50k`) |
| `ValueError: To serve at least one request with the model's max seq len (X), N GiB KV cache is needed ...` | `--max-model-len` is higher than what fits in the available KV pool | Read `estimated maximum model length is M` from the same error and set `--max-model-len ≈ 0.99 × M`. Or run `python windows_tools\probe_max_ctx.py --snapshot snapshots\start_speed.py` |
| `TRITON_ATTN only accepts {"fp8","fp8_e4m3"}` | `fp8_e5m2` copied from a Linux recipe | Change to `fp8_e4m3`. Linux features that ship `fp8_e5m2` and TurboQuant 3-bit don't apply to this wheel. |
| `'GPUModelRunner' object has no attribute 'drafter'` at boot | ngram spec-decode + PP > 1 on vLLM 0.19.0 | Disable spec-decode for any PP > 1 config. See [`SPEC_DECODE_MATRIX.md`](SPEC_DECODE_MATRIX.md) |
| `NotImplementedError: Pipeline parallelism is not supported for this model` | MTP + PP on Qwen3-Next | Pick: TP=1 with MTP, *or* PP=2 with no spec-decode. There's no middle ground on this wheel. |
| `ValidationError: Target and draft model should have the same vocabulary size` | Vocab mismatch (Qwen3 drafter under Qwen3.5/3.6 target) | Qwen3.6-27B is vocab=248320; no small (≤2 B) Qwen3 drafter has that vocab. Don't try to use draft-model spec-decode on this model class. |
| `FileNotFoundError` during first request after fresh boot | FlashInfer JIT tripping ninja MAX_PATH | Use TRITON_ATTN. Pass `--attention-backend=TRITON_ATTN` as a CLI flag (the env var alone is ignored on 0.19.0). |
| TP=2 loads fine but decodes at ~7 tok/s | CPU-relay allreduce dominating per-layer cost | Don't use TP=2 on Windows. Use PP=2 or TP=1. |
| Boot hangs forever in worker | Missing CPU-relay patch (fresh venv rebuild) | `python windows_tools\apply_patches.py --venv venv`. Then `verify_install.py` to confirm. |
| Port 5001 in use | Prior server didn't exit cleanly | `python windows_tools\tune_restart.py --port 5001` sweeps PIDs from the log file and re-launches |
| `zmq.error.ZMQError: Address in use (addr='tcp://127.0.0.1:459NN')` | Orphan EngineCore from previous run still holds an ephemeral ZMQ port | Same — `tune_restart.py` walks every `EngineCore pid=N` line in the log |
| Output appears in `reasoning` field with `content=""` and `finish_reason=length` | `max_tokens` ran out before `</think>` | Raise `max_tokens`, or append `/no_think` to the prompt, or drop `--reasoning-parser qwen3` for that workload |
| `vllm: error: unrecognized arguments: --cuda-graph-sizes ...` | Wrong flag name | It's `--cudagraph-capture-sizes` (no internal hyphen between cuda and graph) |
| `UnicodeEncodeError: 'charmap' codec can't encode character '\u2588'` | Detached launch → stdout falls back to cp1252; vLLM emits progress-bar chars | Already handled in shipped snapshots. If you wrote a custom one: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top of the tee thread |
| Boot wait times out at 120 s | vLLM 27B INT4 takes ~90–110 s to first `Application startup complete` on a 3090 | Increase wait. The launcher polls every 2 s for ~3 minutes by default. |
| `Available KV cache memory: -X.XX GiB` (negative) | Trying to serve on a card where free < model + ~5 GiB activations | This is the GPU0-with-desktop case. Switch to GPU1, or shrink the model, or close everything. Lowering `--max-num-batched-tokens` to 512 saves ~2 GiB activation but rarely enough for 27B. |
| Coherent for 30 tokens then "the the the" mid-sentence | KV-dtype too aggressive for this model class | Drop to BF16 baseline, then step back up. See [`COHERENCE.md`](COHERENCE.md). |
| Tokenizer load fails with "tokenizer_class 'TokenizersBackend' is not recognised" | Lorbus AutoRound's custom class name | `python windows_tools\patch_tokenizer.py G:\_models\Qwen3.6-27B-int4-AutoRound`. Re-run after every model re-download. |
| Coherent output but `draft_acceptance_rate ~ 0.0` | MTP head was quantised to INT4 by the quant author and silently skipped | Use `Lorbus/Qwen3.6-27B-int4-AutoRound` specifically. See [`MTP_HEAD.md`](MTP_HEAD.md). |
| Launcher TUI looks broken in legacy cmd | Console is too old for VT sequences | Install Windows Terminal (free in the Microsoft Store). The launcher tries to relaunch into it automatically. |

## When opening an issue

Please include:

1. GPU model + driver version (`nvidia-smi -q | head -25`)
2. Windows build (`winver`)
3. The snapshot you launched
4. The relevant slice of `logs\vllm_server.<port>.log` — the boot section
   plus 50 lines around the failure
5. Output of `python windows_tools\verify_install.py`
6. Whether the same prompt works on a known-good config (e.g. drop to
   `--enforce-eager`, MTP off, ctx=8000)

The [bug report template](../.github/ISSUE_TEMPLATE/bug_report.md) prompts
for these.

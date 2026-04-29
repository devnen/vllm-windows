# Why Lorbus AutoRound — the MTP head matters

Multi-token prediction (`--speculative-config '{"method":"mtp","num_speculative_tokens":N}'`)
only works if the model weights ship an **MTP head in BF16**. The vLLM
`Qwen3_5MTP` loader looks for tensors named `mtp.fc.*` and refuses (silently)
to use them if they're quantised.

This is why every fast Windows config in this fork uses
[`Lorbus/Qwen3.6-27B-int4-AutoRound`](https://huggingface.co/Lorbus/Qwen3.6-27B-int4-AutoRound)
specifically:

- **Lorbus AutoRound** keeps `mtp.fc` in BF16 (~280 MiB extra), and the loader
  finds it.
- Other Qwen3.6-27B quants — `cyankiwi`, `groxaxo/Qwen3.6-GPTQ-Pro-4bit`, etc.
  — either OOM trying to allocate a fresh BF16 head on a 24 GB card, or
  quantise the head to INT4 along with the body. The loader silently skips
  the quantised head, MTP runs, and you get **0 % draft acceptance** — no
  speedup, no error message.

## How to tell if MTP is actually working

Watch the boot log for:

```
Spec decode metrics: draft_acceptance_rate=0.62, system_efficiency=1.85
```

- `draft_acceptance_rate` should be 0.4–0.7 for prose / mixed content,
  0.2–0.5 for dense code. **If it's near 0.0, your quant's MTP head got
  silently skipped.**
- `system_efficiency` should be > 1.2 to be worth running. < 1.0 means MTP
  is *costing* you tokens — disable it.

Tail the log:

```powershell
Get-Content logs\vllm_server.5001.log -Wait | Select-String 'draft_acceptance|system_efficiency|spec decode'
```

## When picking a different MTP-capable quant

If you want to try a different 27B quant with MTP:

1. **Confirm the model card explicitly mentions a BF16 MTP head.** "Keeps
   `mtp.fc` in BF16" or similar. If the card doesn't say, the head was
   probably quantised with the rest of the body.
2. **Or grep the safetensors index** for `mtp.fc` weights and verify the
   dtype is `BF16`/`F16`:
   ```powershell
   .\venv\Scripts\python.exe -c "from safetensors import safe_open; f=safe_open(r'G:\_models\<model>\model-00001-of-NNN.safetensors','pt'); [print(k, f.get_tensor(k).dtype) for k in f.keys() if 'mtp' in k]"
   ```
3. **Run the launcher's coherence check** with MTP on, watch the
   acceptance rate. If it's near zero, the quant's head is unusable.

## Why you can't have MTP and PP at the same time

`Qwen3_5MTP` worker init refuses pipeline parallelism on Qwen3-Next:

```
NotImplementedError: Pipeline parallelism is not supported for this model
```

This is a vLLM 0.19.0 limitation, not a hardware one. It means: pick MTP
*or* PP (for big context), not both. We chose MTP for the speed snapshots
and added a separate PP=2 snapshot for the rare 160 k-context case. See
[`SPEC_DECODE_MATRIX.md`](SPEC_DECODE_MATRIX.md) for the full compatibility
table.

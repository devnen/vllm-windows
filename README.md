# vllm-windows

> Native Windows fork of [vLLM](https://github.com/vllm-project/vllm) — no
> WSL, no Docker, no conda bootstrap. Prebuilt wheel, portable launcher,
> validated configs for Qwen3.6-27B on RTX 3090 / 4090. **Everything runs
> on your machine. No telemetry, no analytics, no phone-home.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Made for Windows](https://img.shields.io/badge/OS-Windows%2010%2F11-0078d6.svg)](https://www.microsoft.com/windows)
[![GPU](https://img.shields.io/badge/tested-RTX%203090%20%C3%97%202-76b900.svg)](https://www.nvidia.com/)

---

## Why this exists

vLLM is the fastest single-user inference engine on consumer NVIDIA right now.
Most fast Qwen3.6-27B recipes on r/LocalLLaMA assume Linux + Docker + WSL.
That's a tax: one community member measured the same 5090 going from
**85 tok/s in WSL to 160 tok/s in native Ubuntu**. Windows users either
take the WSL hit or don't run vLLM.

This fork is the third option. Same vLLM core, but with the Windows-specific
patches that make it actually work natively, packaged so the install is:

```text
1. Download the launcher zip from Releases.
2. Unzip.
3. Double-click start.bat.
```

No pip, no conda, no `curl | bash`. The launcher ships with an embedded
Python runtime — every dependency is preinstalled inside the zip.

## What you get

**On a single RTX 3090 (24 GB) running Qwen3.6-27B Lorbus AutoRound INT4:**

| Snapshot              | Decode tok/s | Context | Notes                                          |
|-----------------------|--------------|---------|------------------------------------------------|
| `start_speed`         | **64.5**     | 90k     | Peak decode — MTP n=6 sweet spot for long prompts |
| `start_127k`          | 53.4         | 127k    | Maximum context on a single GPU                |
| `start_mtp4`          | 58.3         | 120k    | Mid-balance speed vs context                   |
| `start_72tps`         | ~72 short    | 32k     | Original short-prompt baseline                 |
| `start_pp2_160k` (2× GPU) | 43.5     | 160k    | Pipeline-parallel for the largest contexts     |
| `start_gpu0_50k`      | volatile     | ~9–50k  | Single-GPU users with the display attached     |

All numbers measured on a 24 KB / ~24 k-token Python source-summary prompt.
[Coherence-validated](docs/COHERENCE.md) — TPS without coherence is a lie.

## What's actually in this fork (vs SystemPanic upstream)

Three patches against `SystemPanic/vllm-windows` 0.19.0, full diff in
[`CHANGES_VS_SYSTEMPANIC.md`](CHANGES_VS_SYSTEMPANIC.md):

1. **CPU-relay for Gloo collectives.** Windows has no real NCCL. Pipeline
   and tensor parallelism hang on CUDA tensors without staging through
   pinned CPU buffers. Patches `parallel_state.py`, `cuda_communicator.py`,
   `base_device_communicator.py`. PP=2 works at 43 tok/s; TP=2 works but
   is dominated by CPU-relay and isn't worth using.
2. **Qwen3 reasoning-parser fix** (mirror of upstream PR #35687) so
   `<tool_call>` doesn't get silently swallowed inside an unclosed
   `<think>` block.
3. **Hardwired wildcard model name** — clients no longer need to match
   `--served-model-name` exactly. The fork is single-tenant single-model
   by design.

## Install

**The 60-second path:**

1. Grab `vllm-windows-launcher-portable-x64.zip` from the latest
   [Release](../../releases). Extract anywhere (no admin needed).
2. Either set `VLLM_MODEL_DIR` to your Qwen3.6 weights folder, or drop the
   model into `models\Qwen3.6-27B-int4-AutoRound\` next to the launcher.
3. Double-click `start.bat`. The TUI lists every snapshot. Pick one,
   press Enter, you're serving.

Detailed install (including the wheel-only path for users who already have
their own venv): see [`docs/INSTALL.md`](docs/INSTALL.md).

## Hardware reality

This fork was tuned and tested on:

- Windows 10 Enterprise 22H2
- 2× NVIDIA RTX 3090 (Ampere, sm_86), no NVLink, PCIe Gen 4
- Power cap up to 350 W per card

It **should** work on any Ampere or newer GPU (3090, 4090, 5090, A6000)
running Windows 10/11. It will not work on Pascal/Turing, Intel Arc, or
any AMD card. **One card with the display attached** loses 1–3 GiB of
VRAM to the Windows desktop compositor and another 2–5 GiB to running
apps — see [`docs/WINDOWS_VRAM_HEADLESS.md`](docs/WINDOWS_VRAM_HEADLESS.md)
for the workarounds, and use the `start_gpu0_50k` snapshot when you have
no display-free GPU available.

If you're on a 4090 or 5090, expect higher numbers than ours. If you're on
something else, nothing here is going to work without your own tuning —
that's fine, please share what you find.

## The local-AI ethos

Everything runs on your machine. No telemetry, no analytics, no phone-home,
no cloud inference, no model weights downloaded behind your back. The
launcher never opens an outbound connection except when you explicitly
ask it to (downloading a wheel or a model from HuggingFace). This is in
the spirit of [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/): your
hardware, your weights, your prompts, your business.

The wheel and the launcher are both Apache-2.0 licensed (inherited from
upstream vLLM). Source diff is committed, every patched file is mirrored
in [`windows_patches/`](windows_patches/) for inspection. SHA256 of every
release asset is published alongside the release — verify before
extracting.

## Documentation

- [`CHANGES_VS_SYSTEMPANIC.md`](CHANGES_VS_SYSTEMPANIC.md) — exact diff vs upstream Windows fork.
- [`docs/INSTALL.md`](docs/INSTALL.md) — full install, including wheel-only path.
- [`docs/HARDWARE.md`](docs/HARDWARE.md) — what works, what doesn't, and why.
- [`docs/COHERENCE.md`](docs/COHERENCE.md) — degenerate-output guide and the 3-tier validator.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — every failure mode we've hit, table form.
- [`docs/TUNING.md`](docs/TUNING.md) — the lever set, anti-levers, and how to sweep your own configs.
- [`docs/SPEC_DECODE_MATRIX.md`](docs/SPEC_DECODE_MATRIX.md) — what spec-decode + parallelism combos work on this wheel.
- [`docs/WINDOWS_VRAM_HEADLESS.md`](docs/WINDOWS_VRAM_HEADLESS.md) — how to free VRAM on Windows for the single-GPU case.
- [`docs/HALLUCINATED_FLAGS.md`](docs/HALLUCINATED_FLAGS.md) — flags you'll see online that don't exist on this wheel.
- [`docs/CREDITS.md`](docs/CREDITS.md) — vLLM team, SystemPanic, Lorbus, the community.

## Contributing

Bug reports welcome — please include GPU model, driver version, Windows
build, and the relevant slice of `logs\vllm_server.<port>.log`. The
[issue template](.github/ISSUE_TEMPLATE/bug_report.md) walks you through it.

This fork is intentionally narrow scope: Windows + Ampere/Ada/Blackwell
NVIDIA + Qwen3.6-27B. PRs that extend it to other models on the same
hardware class are welcome. PRs that extend it to other operating systems
or other GPU vendors are politely out of scope here — please go upstream.

## Credits

- [vLLM](https://github.com/vllm-project/vllm) — the engine.
- [SystemPanic/vllm-windows](https://github.com/SystemPanic/vllm-windows) — the Windows wheel this fork is based on.
- [Lorbus](https://huggingface.co/Lorbus) — the AutoRound INT4 quant of Qwen3.6-27B that makes any of this fast.
- The r/LocalLLaMA community — every config in here was informed by their published recipes and brutal honesty in comments.

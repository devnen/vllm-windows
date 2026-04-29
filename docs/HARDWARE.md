# Hardware reality

Honest answers about what works on what.

## Tested

- Windows 10 Enterprise 22H2, 19044.x
- 2× NVIDIA RTX 3090, 24 GB each, Ampere sm_86, no NVLink, PCIe Gen 4 ×16
- Power cap up to 350 W per card (250 W also benchmarked — see TUNING.md)
- 256 GB DDR4 (model weights stream from disk, RAM hardly matters)
- Models live on a separate NVMe; no measurable load-time difference vs system disk

## Should work, untested

- RTX 4090 / 4080 (Ada, sm_89) — same code path; expect higher numbers
- RTX 5090 / 5080 (Blackwell, sm_120) — same code path, even higher numbers
- Single 3090 / 4090 — but see the display-attached caveat below
- A6000 / A40 / data-centre Ampere — in theory; nobody has tested

## Probably won't work without effort

- Windows Server (no Windows Terminal by default — TUI works in cmd but is uglier)
- Pascal / Turing GPUs — sm_86 minimum is hard-coded by `verify_install.py`'s
  warnings; the wheel itself may build kernels for older arches but TRITON_ATTN
  code paths haven't been validated
- WSL2 — works in principle (you'd just install upstream vLLM there) but
  loses 10–15% to virtualisation. Use native Linux if you have the option.
- Hyper-V / DDA passthrough into a Linux VM — not tested; if you do, please
  open an issue with your numbers

## Will not work

- AMD GPUs (RX 6000/7000/9000, Instinct) — vLLM ROCm path doesn't ship in
  this Windows wheel. Use upstream vLLM on Linux.
- Intel Arc / Battlemage — same.
- Apple Silicon — wrong universe; use mlx-lm.
- 16 GB cards (RTX 4060 Ti 16G, 5060 Ti 16G) — Qwen3.6-27B INT4 weights
  alone are 16.96 GiB; you'd need a smaller model. Try Qwen3-14B or
  smaller variants.

## The Windows desktop VRAM tax

The GPU that drives your monitor loses **1–3 GiB** to the Windows desktop
compositor (DWM) before any app is open. Common apps eat more:

| Workload | Extra VRAM |
|---|---|
| Single 1440p SDR monitor, idle desktop | ~0.6–1.0 GiB |
| Dual 4K HDR monitors | ~1.5–2.5 GiB |
| Chrome (10 tabs, HW accel on) | +0.3–0.7 GiB |
| Microsoft Teams, Discord, Outlook | +0.4–1.0 GiB combined |
| dbForge / heavy IDE | +0.5–1.5 GiB |
| 4K YouTube playing | +1.0–1.5 GiB |
| Realistic "office workload" total | ~3–5 GiB |
| Heavy: + 4K media + Snagit | ~5–7 GiB |

So a 24 GiB card with the display attached and a typical workload has
~17–20 GiB *actually free* for vLLM, not 24. Qwen3.6-27B INT4 weights are
16.96 GiB, plus ~5 GiB of activations, plus you want some KV pool — the
math breaks at 24 GiB.

**The default snapshots assume your inference card is display-free.** They
pin `CUDA_VISIBLE_DEVICES=1` and use `--gpu-memory-utilization=0.948`. If
you only have one GPU, those will OOM. Use [`start_gpu0_50k`](../snapshots/start_gpu0_50k.py)
which is conservative (lower mem-util, smaller MNBT, modest ctx) and
expect 9–50 k of usable context depending on what's open.

For permanent VRAM relief on a single-GPU system, see
[`WINDOWS_VRAM_HEADLESS.md`](WINDOWS_VRAM_HEADLESS.md). Short version:
plug a $30 GT 1030 into your monitor, leave the 3090 compute-only.
Or on Intel desktop CPUs, route the display to the iGPU.

## GPU0 vs GPU1 (dual-GPU systems)

If you have two cards and one drives the display:

- **GPU0** (display) — display tax applies. Use `mem_util ≤ 0.92`.
- **GPU1** (no display) — full ~22.76 GiB free after CUDA context init.
  Default snapshots use `mem_util = 0.948` here; 0.95 trips vLLM's safety
  check by ~40 MiB.

The `start_*` snapshots (other than `pp2`) all pin GPU1. If your headless
card is GPU0 instead, edit the snapshot's `CUDA_VISIBLE_DEVICES`
assignment, or set the `CUDA_VISIBLE_DEVICES` env var before launching.

## Power cap

We measured 250 W → 350 W on these cards:
- Prefill: 845 → 983 tok/s (+16 %)
- Decode: unchanged (decode is memory-bandwidth-bound at batch=1)

Default snapshots assume 350 W. Set with `nvidia-smi -pl 350`. **Don't
exceed your PSU's headroom** — two 3090s at 350 W draw ~750 W from the
12V rails alone before CPU and the rest. We're using a 1300 W Gold PSU.

## Tensor vs pipeline parallelism

- **TP=2 on Windows: don't.** Even with the CPU-relay patch, allreduce
  fires every transformer layer and dominates the per-token cost (~7.5
  tok/s on Qwen3.6-27B). PP=2 is far better.
- **PP=2: usable for big context.** ~43 tok/s, ctx up to 160 k. The
  hidden-state hand-off is the only thing crossing CPU per layer.
- **TP=1: the throughput champion** when one card is enough. MTP works.
  64.5 tok/s on the recommended `start_speed` snapshot.

You cannot have MTP and PP at the same time on this wheel — see
[`SPEC_DECODE_MATRIX.md`](SPEC_DECODE_MATRIX.md).

# vllm-windows (devnen patched fork)

> **A patched native-Windows build of [vLLM](https://github.com/vllm-project/vllm).**
> Three Windows-specific fixes on top of [SystemPanic/vllm-windows](https://github.com/SystemPanic/vllm-windows)
> 0.19.0. Source tree, patch backups, and prebuilt wheels.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Made for Windows](https://img.shields.io/badge/OS-Windows%2010%2F11-0078d6.svg)](https://www.microsoft.com/windows)

---

## Looking for the launcher?

If you came here looking for **a one-click way to run Qwen3.6-27B fast on
Windows**, you want the matching launcher repo:

> **[devnen/qwen3.6-windows-server](https://github.com/devnen/qwen3.6-windows-server)** — portable Textual TUI, validated configs, the wheel from this repo bundled inside. Unzip and double-click.

This repo (`vllm-windows`) is the engine layer underneath: the patched
vLLM source, patch backups, and the wheel build. End users normally don't
need it.

## What this fork is

A thin patch series on top of [`SystemPanic/vllm-windows`](https://github.com/SystemPanic/vllm-windows) — the
existing community Windows build of vLLM, base version 0.19.0. We add
three patches that make a few real-world inference workloads actually
work on Windows. The full diff lives at
[`CHANGES_VS_SYSTEMPANIC.md`](CHANGES_VS_SYSTEMPANIC.md).

| # | Patch | Why |
|---|-------|-----|
| 1 | **CPU-relay for Gloo collectives** | Windows has no NCCL. PP/TP collectives hang or `0xC0000005` on CUDA tensors. Patches `parallel_state.py`, `cuda_communicator.py`, `base_device_communicator.py`, `gpu_worker.py` to stage through pinned CPU buffers when `os.name == "nt"`. |
| 2 | **Qwen3 reasoning parser fix** | Mirror of upstream PR [#35687](https://github.com/vllm-project/vllm/pull/35687). Treats `<tool_call>` as an implicit `</think>` so unclosed reasoning blocks don't swallow tool calls. |
| 3 | **Hardwired wildcard model name** | `OpenAIModelRegistry.is_base_model` always returns `True`. Single-tenant single-model deployments shouldn't require clients to match `--served-model-name` exactly. |

Patched files live under `vllm/` (the source tree, what gets built into
the wheel) **and** under `windows_patches/` (verbatim mirror copies, so
the patches survive a clean wheel install — apply them with
`python windows_patches/apply_patches.py --venv <venv>`).

## Install

### Prebuilt wheel (recommended)

Grab the latest `vllm-0.19.0+devnen.<n>-cp312-cp312-win_amd64.whl` from
the [Releases](../../releases/latest) page, then:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install <path-to-downloaded-wheel>
```

The patches are baked into the wheel — no separate apply step needed.
Verify:

```powershell
python windows_patches\verify_install.py --venv .\venv
```

Green output = patches in place.

### From SystemPanic's wheel + patch overlay

If you already have `SystemPanic/vllm-windows` 0.19.0 installed and just
want the patches:

```powershell
git clone https://github.com/devnen/vllm-windows.git
cd vllm-windows
python windows_patches\apply_patches.py --venv <path-to-your-venv>
python windows_patches\verify_install.py --venv <path-to-your-venv>
```

`apply_patches.py` is idempotent. Re-running it after a `pip install
--force-reinstall` of the upstream wheel will re-apply the patches
cleanly.

### From source

CUDA 12.6, MSVC 2022 Community, PyTorch 2.11.0+cu126. Build follows
SystemPanic's [original instructions](https://github.com/SystemPanic/vllm-windows#building-from-source)
verbatim — we don't change the build system. Expect 2–4 hours on a
5950X-class machine.

## What this repo is _not_

- **Not** a fork tracking `vllm-project/main`. Base is
  `SystemPanic/vllm-windows` at commit `76aefe152`. Newer SystemPanic
  releases are reachable via the `upstream` git remote but the patches
  here target the 0.19.0 internals (which got refactored upstream).
- **Not** a launcher / app / TUI. That's
  [`devnen/qwen3.6-windows-server`](https://github.com/devnen/qwen3.6-windows-server).
- **Not** scope-broadened to other operating systems or non-NVIDIA GPUs.

## What's in the box

```
vllm/                       Patched vLLM source tree (what gets built).
windows_patches/            Patch mirror copies + apply/verify scripts.
  README.md                 Per-file root-cause + diff explanation.
  apply_patches.py          Overlay patches onto an existing venv.
  verify_install.py         sha256 check the in-venv files match windows_patches/.
  *.py                      Patched file copies.
CHANGES_VS_SYSTEMPANIC.md   Commit-by-commit diff vs the upstream Windows fork.
```

## Compatibility

Wheel built against:

- Python 3.12.x
- CUDA 12.6
- PyTorch 2.11.0+cu126 (matching torch nightly index URL in upstream
  build instructions)
- Windows 10 / 11 x64
- NVIDIA Ampere (sm_86) or newer

Nothing exotic about the build vs SystemPanic's wheel — same toolchain,
same CUDA, same Python. Only the source diff changes.

## Contributing

Bug reports for the **patches** (CPU-relay regressions, parser quirks,
model-name acceptance) are welcome. Bug reports for upstream vLLM
behaviour should go to [`vllm-project/vllm`](https://github.com/vllm-project/vllm/issues).
Bug reports for the Windows build toolchain should go to
[`SystemPanic/vllm-windows`](https://github.com/SystemPanic/vllm-windows/issues).
Bug reports for the user-facing launcher should go to
[`devnen/qwen3.6-windows-server`](https://github.com/devnen/qwen3.6-windows-server/issues).

## Credits

- [vLLM](https://github.com/vllm-project/vllm) — the engine. Apache-2.0.
- [SystemPanic/vllm-windows](https://github.com/SystemPanic/vllm-windows) — the upstream Windows wheel build infrastructure this fork is based on.
- [Qwen team](https://huggingface.co/Qwen) — the model class these patches happen to be tuned for.
- Upstream PR [#35687](https://github.com/vllm-project/vllm/pull/35687) — origin of the Qwen3 reasoning parser fix mirrored here.

## License

Apache-2.0, inherited from upstream vLLM. See [`LICENSE`](LICENSE).

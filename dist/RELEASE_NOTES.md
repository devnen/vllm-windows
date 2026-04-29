# vLLM 0.19.0+devnen.<N> — patched native-Windows build

A repackaging of [`SystemPanic/vllm-windows`](https://github.com/SystemPanic/vllm-windows)
0.19.0 with three Windows-specific patches applied. Python 3.12, win_amd64.

## What's patched (vs SystemPanic/vllm-windows 0.19.0)

1. **CPU-relay for Gloo collectives.** Windows has no NCCL. PP/TP collectives hang or `0xC0000005` on CUDA tensors. Patches `parallel_state.py`, `cuda_communicator.py`, `base_device_communicator.py`, and `gpu_worker.py` to stage through pinned CPU buffers when `os.name == "nt"`.
2. **Qwen3 reasoning parser fix.** Mirror of upstream PR [#35687](https://github.com/vllm-project/vllm/pull/35687).
3. **Hardwired wildcard model name.** `OpenAIModelRegistry.is_base_model` always returns `True`; clients no longer need to match `--served-model-name`.

Full diff: [`CHANGES_VS_SYSTEMPANIC.md`](https://github.com/devnen/vllm-windows/blob/main/CHANGES_VS_SYSTEMPANIC.md).

## Install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install <url-to-wheel>
python windows_patches\verify_install.py --venv .\venv
```

## SHA256

```
8f537f97a9fb00c0504ca644671c13a3df33ccf663ba5c40612f388c79dc4471  vllm-0.19.0+devnen.1-cp312-cp312-win_amd64.whl
```

PowerShell: `Get-FileHash vllm-0.19.0+devnen.1-cp312-cp312-win_amd64.whl -Algorithm SHA256 | Format-List`.

## Looking for a one-click launcher?

Use [`devnen/qwen3.6-windows-server`](https://github.com/devnen/qwen3.6-windows-server)
— portable zip, embedded Python, this wheel bundled in.

## Compatibility

- Windows 10 / 11 x64
- Python 3.12.x
- NVIDIA Ampere `sm_86` or newer

## License

Apache-2.0, inherited from upstream vLLM.

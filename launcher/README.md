# vllm-windows launcher

A small Textual-based TUI that lists every validated config in this fork as a
launchable card. Pick one with arrow keys, hit Enter, the server starts on
its assigned port. No yaml editing, no command lines.

## Running it

**Portable zip release (recommended)** — unzip the
`vllm-windows-launcher-portable-x64.zip` from the GitHub Release, then
double-click `start.bat` at the top of the folder. That's the entire
install — Python, Textual, every dependency is already bundled.

**Developer checkout** — from the repo root with a venv that has the
launcher deps installed (`pip install textual rich httpx pyyaml`),
double-click `launcher\start.bat` or run:

```cmd
launcher\start.bat
```

## Settings the launcher reads

The TUI reads `launcher\configs.yaml`. Every entry under `windows.configs`
shows up as a card. Placeholders inside the yaml are resolved against
environment variables:

| Placeholder         | Default                                                      | Override via env |
|---------------------|--------------------------------------------------------------|------------------|
| `${SNAPSHOTS_DIR}`  | `<repo>\snapshots`                                           | `VLLM_WINDOWS_SNAPSHOTS` |
| `${MODEL_DIR}`      | `<repo>\models\Qwen3.6-27B-int4-AutoRound`                   | `VLLM_MODEL_DIR` |
| `${LOG_DIR}`        | `<repo>\logs`                                                | `VLLM_WINDOWS_LOGS` |

Set those env vars *before* launching to point the launcher at your model
weights and snapshot directory without editing any yaml.

The Linux/remote-host tab is hidden by default in this release. To re-enable
once it's been re-tested in a follow-up:

```cmd
set VLLM_WINDOWS_ENABLE_LINUX=1
launcher\start.bat
```

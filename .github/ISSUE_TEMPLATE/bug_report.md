---
name: Bug report
about: Something is broken
title: "[bug] "
labels: bug
---

## What happened

(Describe the failure in 1–3 sentences.)

## Hardware + OS

- GPU(s) — model and driver version (`nvidia-smi -q | head -25`)
- Windows build (`winver` — paste the build number)
- CPU + RAM (relevant only for very large prefills)
- Single GPU? Is the display attached to it?

## Install path

- [ ] Portable launcher zip
- [ ] Wheel-only install into my own venv
- [ ] Built from source

vLLM version (`python -c "import vllm; print(vllm.__version__)"`):

## Snapshot you tried

`start_speed` / `start_127k` / `start_pp2_160k` / other (specify):

## Reproducer

(The exact command or click sequence that triggered the failure.)

## Logs

Paste the boot section of `logs\vllm_server.<port>.log` (first ~50 lines)
plus the last ~50 lines around the failure. Don't worry about size — we'd
rather have too much than too little.

```
(paste here)
```

## Verifier output

```
python windows_tools\verify_install.py --venv .\venv
```

```
(paste here)
```

## What you've already tried

(e.g. dropped to enforce-eager, disabled MTP, ran the coherence check, etc.)

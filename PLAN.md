# Ultimate Plan: ship `devnen/vllm-windows` to the community

Synthesised from research on how KoboldCpp / llama.cpp / oobabooga / LM Studio
distribute on Windows + r/LocalLLaMA's stated preferences. Three insights drove
the design:

1. **Power users want prebuilt wheels via GitHub Releases.** That's the highest-
   trust delivery format. Provenance signals matter: SHA256, CI build log,
   readable diff vs upstream, candid hardware docs.
2. **Beginners want "unzip → double-click → it runs"** (oobabooga's portable
   zip got the strongest positive Reddit reception of all the tools surveyed).
   That implies an embeddable-Python launcher folder, not a conda bootstrap.
3. **The biggest complaints** are CUDA-version hell, undocumented hardware
   requirements, dependency-soup forks that need other forks, and stale Docker
   images. None of those apply to us if we're disciplined about scope and docs.

Our scope is narrow on purpose: **single Windows runtime, single CUDA version
(12.6, the SystemPanic wheel target), single GPU class (Ampere/sm_86 — what
tested), single model class (Qwen3.6-27B AutoRound INT4)**. Pretending to
support more is what gets forks called sketchy.

## Final repo layout

```
vllm-windows/                       (this fork — devnen/vllm-windows)
├── README.md                       — friendly hook, hero numbers, quickstart
├── BENCHMARKS.md                   — full sweep tables (n=3..8, ctx, 250W vs 350W)
├── CHANGES_VS_SYSTEMPANIC.md       — (exists) commit-by-commit fork delta
├── PLAN.md                         — (this file)
├── LICENSE                         — Apache-2.0 (inherited from vLLM)
├── CITATION.cff                    — academic-style citation block
├── docs/
│   ├── HARDWARE.md                 — what works (2×3090 Ampere), what doesn't
│   ├── INSTALL.md                  — 3-step install (download, extract, run)
│   ├── COHERENCE.md                — degenerate-output guide + harness usage
│   ├── TROUBLESHOOTING.md          — every failure mode from the skill, table form
│   └── CREDITS.md                  — vLLM team, SystemPanic, Lorbus
├── vllm/                           — patched source (already in repo)
├── windows_patches/                — (exists) patch backups
├── launcher/                       — portable TUI launcher (NEW)
│   ├── start.bat                   — entry: double-click → TUI
│   ├── setup.bat                   — one-time: downloads embed-python + deps
│   ├── README.md                   — launcher quickstart
│   ├── app/                        — vllm_launcher package (renamed from vllm-turbo)
│   │   ├── __main__.py
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── inference.py
│   │   ├── runtime.py
│   │   ├── linux_runtime.py        — keep, but optional/disabled by default
│   │   ├── serve.py
│   │   ├── screens/
│   │   └── widgets/
│   ├── configs.yaml                — sanitized: ${MODEL_DIR} / ${VLLM_DIR} placeholders
│   ├── configs.user.example.yaml   — copy-and-edit template for user paths
│   └── python/                     — embeddable Python 3.12, .gitignore'd, populated by setup.bat
├── snapshots/                      — start_*.py + .bat scripts (NEW)
│   ├── README.md                   — table of snapshots, when to use which
│   ├── start_speed.py / .bat       — 64.5 tok/s peak decode (MTP n=6)
│   ├── start_127k.py / .bat        — 127k max ctx (MTP n=3)
│   ├── start_mtp4.py / .bat        — mid-balance
│   ├── start_pp2_160k.py / .bat    — 160k ctx via PP=2 (kills MTP)
│   ├── start_72tps.py / .bat       — original short-prompt baseline
│   └── start_gpu0_50k.py / .bat    — single-GPU-with-display fallback (see below)
├── windows_tools/                        — helper utilities (NEW)
│   ├── apply_patches.py            — overlay windows_patches/ onto a venv
│   ├── check_coherence.py          — 3-tier coherence battery (capital / Whiskers / Fibonacci)
│   ├── bench.py                    — streaming TPS bench client
│   ├── bench_summarize.py          — 24k-token code-summary prefill+decode bench
│   ├── tune_restart.py             — kill :PORT + sweep EngineCore PIDs + relaunch
│   └── verify_install.py           — sanity check: wheel + patches + GPU visible
├── .gitignore                      — venv, models, launcher/python, runs.tsv, logs
└── .github/
    ├── workflows/
    │   └── release.yml             — manually-triggered: builds patched wheel + portable zip + SHA256SUMS
    └── ISSUE_TEMPLATE/
        └── bug_report.md           — must include: GPU model, driver, OS build, vllm log
```

## Distribution model (GitHub Releases)

Tag pattern: `v0.19.0-devnen.<n>` (e.g. `v0.19.0-devnen.1`). Each release ships:

| Asset | Size | Purpose |
|---|---|---|
| `vllm-0.19.0+devnen.<n>-cp312-cp312-win_amd64.whl` | ~250 MB | Patched vLLM wheel — `pip install <url>` and done |
| `vllm-windows-launcher-portable-x64.zip` | ~80–120 MB | Self-contained: embed python + deps preinstalled + launcher source. Unzip, double-click `start.bat` |
| `SHA256SUMS.txt` | 1 KB | One line per asset |
| `README.md` (release notes) | — | What changed since previous tag, hardware tested on |

End-user happy path:

```
1. Download vllm-windows-launcher-portable-x64.zip from Releases.
2. Extract anywhere (no admin needed).
3. Double-click start.bat. Launcher TUI opens.
4. First-run wizard:
   a. Detect GPU (nvidia-smi). Refuse to proceed if not Ampere/Ada.
   b. Prompt for model path (tab-complete a folder).
   c. Offer: "Install vLLM wheel into ./venv? (y/n)" — fetches the .whl from
      this release, runs pip install, applies windows_patches.
   d. Coherence test: "Run 3-tier check? (recommended)" — one click validation.
5. Pick a snapshot from the TUI (Speed king, Max ctx, etc). Hit Enter. Server
   starts on port 5001/5002/5003.
```

## Phasing

### Phase 1 — Repo restructure + docs (today, no external assets)

- Move launcher source from `C:\_projects\vllm-turbo\launcher\vllm_launcher\` into `launcher/app/` in this repo.
- Sanitize `configs.yaml`: replace hardcoded `G:\_models\…` and `C:\_projects\…` with `${MODEL_DIR}` / `${VLLM_TURBO_DIR}` placeholders, resolved by `app/config.py` against env vars or a `configs.user.yaml` overlay.
- Move `start_*.py` + `.bat` into `snapshots/`. Update internal paths to use `${VLLM_VENV}` / `${MODEL_PATH}` resolved from env or `.env` file at repo root.
- Move bench / coherence / tune scripts into `windows_tools/`. Adapt `bench.py` to read port from `--port` rather than hardcoded 5001.
- **Hard requirement: end users do NOT run pip, conda, or any installer.** The
  shipped `vllm-windows-launcher-portable-x64.zip` contains the embeddable
  Python with every dependency *already installed* into `python\Lib\site-packages\`.
  Unzip → double-click `start.bat` → TUI opens. That's the whole UX.
- `windows_tools/build_launcher_zip.py` (developer-side, NEVER shipped to users) —
  one command we run before tagging a release:
  1. Downloads `python-3.12.X-embed-amd64.zip` into a temp dir.
  2. Extracts to `launcher/python/`.
  3. Edits `python312._pth` to add `Lib\site-packages` and uncomment `import site`.
  4. Bootstraps pip via `get-pip.py` (one time, into the embed).
  5. `python.exe -m pip install --no-warn-script-location textual rich httpx pyyaml` into the embed.
  6. **Removes `pip`, `setuptools`, `wheel`, `__pycache__/`, `*.pyc`, and the `Scripts/` directory** from the final tree — users have no need for pip and shipping it just makes the zip bigger and more confusing.
  7. Archives `launcher/` into the release zip with `python/` populated.
- `launcher/start.bat` (USER-FACING entry point — the only thing the end user touches):
  - Uses `%~dp0` so the whole tree is relocatable anywhere on disk.
  - Sets `PYTHONHOME=%~dp0python`, leaves system `PATH` untouched (avoid DLL bleed).
  - Sets `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1` (the launcher emits unicode block chars in progress bars).
  - Runs `"%~dp0python\python.exe" -m app %*`.
  - Does NOT call pip, does NOT need internet, does NOT touch the registry.
- **Verification before tagging a release:** `windows_tools/test_portable_zip.py` — extracts the zip into `%TEMP%\vllm-windows-portable-test\`, double-clicks `start.bat`, asserts the TUI launches without errors. Catches the "forgot to ship a dep" class of bug before users see it.
- Friendly `README.md` rewrite: hero number ("64.5 tok/s decode on a single 3090"), screenshot of TUI, 3-step quickstart pointing to the latest release, why-this-fork-exists (3 patches), candid caveats.
- `docs/` skeleton + `CITATION.cff`.
- Commit + push to `devnen/vllm-windows`. End state: repo is browsable and the launcher source is in tree, but the prebuilt zip and wheel are not yet attached to a release.

### Phase 2 — Build + upload release assets (one human-attended pass)

- **Patched wheel.** Two options:
  - **(A) Repackage SystemPanic's wheel.** Unzip the existing installed wheel from the user's venv, overlay our patched `vllm/` files, re-zip with bumped version `0.19.0+devnen.1`. Fast (minutes), preserves all binary artifacts. License-clean under Apache-2.0 with attribution + modification notice. Recommended.
  - **(B) Rebuild from source.** Use SystemPanic's build setup against our patched tree. Hours. Only if (A) hits a problem.
- **Portable launcher zip.** Run `setup.bat` once, archive the resulting `launcher/` folder (with `python/` populated) into `vllm-windows-launcher-portable-x64.zip`.
- **SHA256SUMS.txt.** Generate via `Get-FileHash`.
- **Release notes.** Hand-written, list the 3 patches and what hardware tested.
- User pushes the release tag + uploads assets via `gh release create`.

### Phase 3 — CI automation (optional, do if Phase 2 works)

- `.github/workflows/release.yml` triggered on `v*` tag push:
  1. Checkout.
  2. Download SystemPanic wheel (cached).
  3. Repackage with our patched `vllm/` tree.
  4. Build launcher portable zip (download embed python, pip install, archive).
  5. Compute SHA256SUMS.
  6. `gh release upload` the artifacts.
- Means future patches → tag → release just works.

## Decisions confirmed

1. **Repackage SystemPanic wheel as `0.19.0+devnen.1`.** Yes.
2. **Linux launcher tab disabled** for v1 (separate session to address; code stays in tree gated behind a config flag, hidden from the dashboard).
3. **No telemetry, ever.** This is a 100% open-source / private / offline / local-only release. That ethos is the framing for every doc — written in the spirit of r/LocalLLaMA where the whole point is *running models without sending data anywhere*. README hero, INSTALL, BENCHMARKS, all of it should lean into "your hardware, your model weights, your network never leaves the machine."
4. **Repo description**: "vLLM fork tuned for Windows + 2× RTX 3090. 64.5 tok/s on Qwen3.6-27B INT4. Portable launcher, validated configs, 100% local." Topics: `vllm`, `windows`, `local-llm`, `qwen3`, `rtx-3090`, `inference`, `local-ai`, `privacy`.

## Items lifted from the vllm-windows skill that were missing

Re-read pass. These need to be in tree before Phase 1 ships, not as Phase 2 nice-to-haves:

### Single-GPU-with-display config (`start_gpu0_50k`)

Most users will have ONE GPU, and on Windows that GPU drives the display —
so `dwm.exe` + browser/IDE accelerated rendering eats 1–3 GiB of VRAM
before vLLM even starts. The standard snapshots (`start_speed`,
`start_127k`, etc.) assume a *display-free* GPU and pin
`CUDA_VISIBLE_DEVICES=1`. They will OOM on a typical single-GPU box.

`start_gpu0_50k.py` exists in the user's vllm-turbo tree as the
single-GPU-with-display fallback: lower mem-util, smaller `MNBT`, modest
ctx (~50k once the desktop tax is paid). It must be a first-class snapshot
in the launcher with a clear card explaining: *"use this if your monitor
is plugged into the same card you're trying to inference on."* The doc
should call out the VRAM-tax range (1–3 GiB display + Chrome/etc adds
2–5 GiB more) and link to `docs/WINDOWS_VRAM_HEADLESS.md` (research in
progress) for ways to reduce it.

The `configs.yaml` card for this snapshot needs `tier: active`,
`status: conditional` (not `recommended` — only relevant for the
single-GPU case), and `notes` calling out that decode TPS will be
volatile run-to-run because background apps shift VRAM by ±2 GiB.

### Hardware-class refusal in launcher first-run
- Detect via `nvidia-smi --query-gpu=name,compute_cap`. Refuse on non-Ampere/non-Ada (sm_86 or higher). Print a candid message — "this fork was tuned on 2× 3090; RDNA / Pascal / Turing not supported, bring your own settings if you try."

### Model-side patches users have to apply (skill section "Bringing up a new model")
- **`windows_tools/patch_tokenizer.py`** — Lorbus AutoRound ships `tokenizer_class: TokenizersBackend` which transformers 4.57 doesn't recognize. Patch to `Qwen2Tokenizer`, save `.bak`, re-patch idempotently after re-download.
- **`windows_tools/verify_model_sha.py`** — fetches HuggingFace `x-linked-etag` per shard, sha256sum's the local file, reports mismatches. Anchor the awk to start-of-line (the skill flagged the `access-control-expose-headers` false-fire).

### Bench harness needs a portable test prompt
- Skill bench uses `C:\_projects\windows-service\service.py` (private code) as the 24k-token prompt. Ship a public-domain alternative — e.g., a vendored snapshot of CPython's `Lib/inspect.py` or a Project Gutenberg text scaled to ~24k tokens. Document the substitution.

### Coherence battery — verbatim from skill
- `windows_tools/check_coherence.py` — three prompts: "What is the capital of France? One sentence." (200 tok), 300-word Whiskers rooftop garden story (700 tok), Fibonacci with docstring (500 tok). Detect degenerate attractors: `* * * *`, `the the the`, `**:**:**`, `\n\n\n\n`, mid-sentence collapse. Exit non-zero on any hit.

### `tune_restart.py` made portable
- Currently hardcodes port 5001 and `vllm_server.log` path. Rewrite with `--port` and `--log` args. Sweeps `EngineCore pid=N` / `APIServer pid=N` regex from log so orphan ZMQ ports get cleaned (the `Address in use (addr='tcp://127.0.0.1:459NN')` failure mode).

### `windows_tools/probe_max_ctx.py`
- Implements the skill's auto-probe oracle: launch with `--max-model-len=200000`, parse the `estimated maximum model length is N` line from stderr, kill, report N. One-shot, no human in the loop.

### Reasoning-parser escape hatch documented
- Skill calls out: `--reasoning-parser qwen3` can produce empty `content` with the answer trapped in `reasoning` if `max_tokens` runs out before `</think>`. Document in `docs/TROUBLESHOOTING.md`: raise `max_tokens`, or append `/no_think` to the prompt, or drop the parser flag.

### MSVC env overlay
- `msvc_env()` pattern in `start.py` captures `vcvars64.bat` env so vLLM subprocess can JIT-compile triton kernels. If the user has only CUDA runtime (no MSVC), capture should fail loudly with a helpful message, not silently. Document MSVC 2022 Community as the supported toolchain.

### Logs directory convention
- All snapshot logs go to `logs/` at repo root (or `%LOCALAPPDATA%\vllm-windows\logs\` if installed system-wide). Rotated `vllm_server.log.<port>` filenames.

### `stop_vllm.bat` / `stop_vllm.py`
- Already exists in vllm-turbo. Port. Should support `--port N` and `--all`.

### Documentation lifts (no code work, just docs)
Each gets its own page or a section, all framed in the local-AI / privacy ethos:

- **`docs/HARDWARE.md`** — what works, what doesn't:
  - 2× RTX 3090, Ampere sm_86 — tested.
  - GPU0 with desktop load: unusable for 27B (4.8 GiB held by display+apps; model alone is 16.96 GiB).
  - TP=2 on Windows: works after CPU-relay patch but ~7.5 tok/s (allreduce dominates) — don't.
  - PP=2: usable, ~43 tok/s, kills MTP.
- **`docs/SPEC_DECODE_MATRIX.md`** — the PP × MTP × ngram × draft-model compatibility table from the skill, verbatim.
- **`docs/MTP_HEAD.md`** — why Lorbus AutoRound is the only 27B INT4 quant that works (BF16 `mtp.fc`); other quants quantize the head and get 0% draft acceptance silently.
- **`docs/COHERENCE.md`** — degenerate-attractor patterns, when KV-dtype is too aggressive, "TPS without coherence is a lie."
- **`docs/HALLUCINATED_FLAGS.md`** — list of flags users will copy from Reddit/Perplexity that don't exist on 0.19.0: `VLLM_FLASHINFER_FORCE_TENSOR_CORES`, `VLLM_USE_FLASH_ATTN_3`, `--decode-threshold`, `--scheduler-delay-mult`, `int8`/`NVFP4`/`MXFP4` `--kv-cache-dtype`. Plus the `--cuda-graph-sizes` vs `--cudagraph-capture-sizes` naming trap.
- **`docs/TUNING.md`** — the lever set: MTP n=6 sweet spot (long prompts), n=3 (short), 250 W → 350 W (+16% prefill, no decode change), `gpu-memory-utilization` ladder (0.92 / 0.94 / 0.948), `--max-num-batched-tokens` non-monotonic peak at 4128, anti-levers (don't bother) list.

### Sanity-check helper
- **`windows_tools/verify_install.py`** — checks: vLLM importable, version is `0.19.0+devnen.*`, all 6 patched files in `windows_patches/` match the in-venv copies (sha256), `nvidia-smi` reports a sm_86+ GPU, MSVC `cl.exe` resolvable. Exits with a green/red summary.

### `runs.tsv` schema documented
- Header: `label\tkv_pool_GiB\tctx\tmtp_n\tprefill_tok_s\tdecode_tok_s\tttft_s\twall_tok_s\tprompt_tokens\tcompletion_tokens\tnotes`. Bench scripts append; users can diff configs.

### Privacy / openness ethos in copy
Every doc opens with a line that lands the framing. Suggested boilerplate for the README:

> Everything in this repo runs on your machine. No telemetry, no analytics, no
> phone-home, no cloud inference. The model weights stay where you put them.
> The launcher never opens an outbound connection except when you explicitly
> ask it to download a wheel or model. This is in the spirit of r/LocalLLaMA:
> your hardware, your weights, your prompts, your business.

After your answers, I execute Phase 1 in one pass and report back. Phase 2 needs you driving the actual `gh release` upload (one terminal command at the end).

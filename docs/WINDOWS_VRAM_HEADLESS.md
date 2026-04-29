# Windows VRAM and headless GPU — what's actually possible

> Why this exists: on Windows the GPU that drives your display loses 1-3 GiB
> of VRAM to the desktop compositor (DWM) and another 2-5 GiB to running apps
> (Chrome, Outlook, Teams, Discord, dbForge, Snagit). For a 24 GB card running
> a 27B INT4 model in vLLM, that tax is the difference between fitting and
> OOMing. This doc quantifies the tax, explains why Windows cannot truly run
> headless the way Linux can, and ranks the workarounds that actually work in
> late 2025 / early 2026.

## TL;DR

- **TCC mode is dead on consumer GeForce.** RTX 3090, 4090, and 5090 cannot
  be flipped to TCC. NVIDIA restricts TCC to Quadro / Tesla / data-center
  SKUs and has done so since the Turing era. WDDM is your only option on a
  GeForce card under Windows.
- **The cheapest real fix is a second GPU for display** (any GT 1030 / RX 6400
  / used GTX 1650). Plug your monitors into it, set the 3090 to "high
  performance" / not connected to a display, and you reclaim 1.5-4 GiB on the
  compute card. Works on AMD AM4/AM5 systems that have no iGPU.
- **On Intel desktop CPUs (LGA1700, UHD 770) you can route the display to
  the iGPU** for free, same effect as a secondary GPU. Enable iGPU in BIOS,
  plug the monitor into the motherboard, set the dGPU as "high performance"
  in Windows graphics settings.
- **WSL2 does NOT free host VRAM.** The GPU is shared with the Windows host
  via GPU-PV; DWM keeps its allocation. You also pay a small CUDA overhead
  inside WSL. Use WSL2 for Linux-only software, not for VRAM relief.
- **Disabling HW acceleration in Chrome / Edge / Teams / Discord / Office
  saves 1-3 GiB realistically.** This is the highest-leverage zero-cost
  knob. Combined with closing Outlook / Snagit while running vLLM, a single
  3090 can plausibly host Qwen3-27B INT4 at 16-32k context.
- **If you have 2 GPUs, this project's default is right:** display on GPU0,
  vLLM on GPU1. Don't overthink it.

## The desktop VRAM tax — measured

Numbers below are typical ranges from multiple sources (r/Windows11,
r/nvidia, techtactician, Microsoft Q&A). Exact figures vary with monitor
count, refresh rate, color depth, and driver version, so always confirm on
your own box with `nvidia-smi`.

| State                                       | GPU0 VRAM used |
|---------------------------------------------|----------------|
| Boot, login screen                          | ~0.3-0.5 GiB   |
| 1080p single SDR monitor, DWM only          | ~0.4-0.7 GiB   |
| 1440p single SDR monitor, DWM only          | ~0.6-1.0 GiB   |
| 4K SDR single monitor, DWM only             | ~0.8-1.2 GiB   |
| 4K + HDR single monitor, DWM only           | ~1.2-1.8 GiB   |
| Dual 4K HDR, DWM only                       | ~1.5-2.5 GiB   |
| + Chrome (10 tabs, HW accel on)             | +0.3-0.7 GiB   |
| + Microsoft Teams (idle)                    | +0.1-0.3 GiB   |
| + Discord (HW accel on)                     | +0.2-0.4 GiB   |
| + Outlook (new) + Office apps               | +0.1-0.3 GiB   |
| + VS Code                                   | +0.1-0.25 GiB  |
| Realistic "office workload" total           | ~3-5 GiB       |
| Heavy: + dbForge + 4K YouTube + Snagit      | ~5-7 GiB       |

How to measure on your own box:

```powershell
# One-shot
nvidia-smi --query-gpu=index,name,memory.used,memory.free --format=csv

# Continuous, 1 Hz
nvidia-smi dmon -s u -i 0
```

The number that matters for vLLM is `memory.free` on the device you pass
as `CUDA_VISIBLE_DEVICES`. vLLM's `--gpu-memory-utilization` is computed
against `memory.total`, so on a display-attached 24 GiB card you usually
want `0.80-0.85` rather than the default `0.90`, otherwise the KV cache
allocator will collide with whatever Chrome decides to allocate next.

Rule of thumb for a 24 GiB display GPU running a typical office workload:
**budget 19-20 GiB for vLLM, not 22-23**.

## Can Windows run truly headless? (like Linux)

**Short answer: no, not in the Linux sense.** Long answer:

- The Windows Desktop Window Manager (`dwm.exe`) is mandatory on Windows 8
  and later. You can kill it; it respawns within ~1 second under Session
  Manager. Even if you stop the service, the GPU driver's WDDM allocation
  stays — the driver itself reserves a chunk of VRAM for paging buffers,
  the framebuffer, and PCIe BAR mappings whenever a display is attached.
- Pulling the monitor cable does not help. The driver still treats the GPU
  as a display device and keeps the framebuffer mapped, because Windows
  composites to a "phantom" display when no monitor is connected so RDP
  and remote tools keep working.
- Stopping the Plug-and-Play display device (Device Manager → Disable) does
  free most of that allocation, but it also disables the GPU for D3D and
  in many driver versions for CUDA as well. This is not a real workaround
  for a single-GPU box.
- There is no "compute-only" toggle in the consumer driver. That toggle is
  TCC mode, and it's locked out (see below).
- Windows Server Core has no DWM by default and gets you closer to "headless,"
  but the NVIDIA consumer driver on Server SKUs is unsupported and the
  Studio/Game Ready installers refuse to run. The data-center driver works,
  but it's licensed for Tesla/A-series cards.

So on consumer Windows with a GeForce card, you will always pay a 0.8-1.5 GiB
WDDM driver tax even with zero apps open. Everything above that is
**discretionary** and can be clawed back.

## Practical workarounds — ranked by effort vs VRAM freed

### 1. Move display to iGPU (Intel desktop CPUs only) — ~2-4 GiB freed, free

If you're on LGA1700 (12th/13th/14th gen Core) or LGA1851 (Core Ultra 200S),
your CPU has UHD 770 / Xe-LP integrated graphics. AMD desktop CPUs without
the `G` suffix (5800X, 7700X, 9800X3D, etc.) **do not have an iGPU** —
skip to workaround #2.

Procedure:

1. Reboot to BIOS. Navigate to **Advanced → System Agent (SA)
   Configuration → Graphics Configuration** (ASUS Z790/B760 layout;
   Gigabyte and MSI label them similarly under "Chipset" / "Onboard
   Devices").
2. Set **Primary Display** / **Initiate Graphic Adapter** to **IGFX** (also
   labelled "CPU Graphics" or "Internal Graphics").
3. Set **iGPU Multi-Monitor** (a.k.a. **IGFX Multi-Monitor**) to **Enabled**.
   This is the key toggle — without it, most boards auto-disable the iGPU
   the moment a dGPU is detected.
4. Bump **DVMT Pre-Allocated** from Auto (~64 MB) to **512 MB or higher**
   for smoother desktop, especially at 4K. The iGPU draws its framebuffer
   from system RAM, so dual-channel DDR5 is strongly recommended.
5. Save, power off, move the display cable from the dGPU to the
   motherboard's HDMI/DP port.
6. Boot Windows. Install the latest Intel Graphics Driver (32.x supports
   11th-14th gen). Keep the NVIDIA driver as-is.
7. `nvidia-smi` should now show GPU0 at ~0.3-0.5 GiB at idle instead of
   1.0-1.5 GiB. DWM follows the cable — no Windows toggle is needed.
   You can also assign `dwm.exe` to "Power Saving" in Settings →
   Display → Graphics as a belt-and-suspenders measure (results are
   inconsistent; the cable does the real work).
8. CUDA continues to enumerate the 3090 even with no display attached.

Caveats:

- **Refresh rate**: UHD 770 caps at 4K@60 Hz. A 4K@120/144 Hz monitor
  drops to 60 Hz on the iGPU. At 1440p you can reach ~165 Hz over DP.
- **HDR**: HDR10 works but tone-mapping is weaker than the 3090's;
  Auto HDR in particular feels sluggish. 10-bit color further reduces
  the max refresh rate.
- **Multi-monitor**: UHD 770 supports up to 4 displays in spec, but most
  motherboards only expose 2 ports (1× HDMI + 1× DP). For 3+ monitors,
  see workaround #2.
- **NVENC / hardware encoding** for OBS, streaming, and video editors
  still runs on the 3090 — that does not move with the cable.
- **Cross-adapter composition**: if any app explicitly renders on the
  3090 and composites on the iGPU, Windows still allocates a small share
  buffer on the 3090. Real-world savings are typically 2-4 GiB, not a
  clean zeroing.

### 2. Cheap secondary GPU for display — ~2-4 GiB freed, $50-150

If you have no iGPU (most AM4/AM5 systems, Threadripper, older Intel HEDT),
add a low-end card purely for display. Good options as of late 2025:

| Card           | Power   | Used price  | Notes                              |
|----------------|---------|-------------|------------------------------------|
| GT 1030 (DDR4) | 30 W    | $40-60      | Two outputs, slot-powered, fine for 1-2 monitors at 1080p/1440p. Avoid for 4K. |
| GTX 1650       | 75 W    | $80-110     | Slot-powered, 4 outputs, 4K60 fine. Best balance. |
| RX 6400        | 53 W    | $90-130     | AMD, slot-powered, single-slot, good for 4K. Mixing AMD+NV drivers is fine on Win11. |
| Arc A310       | 75 W    | $100-130    | Modern, AV1 decode/encode, four outputs. |

Procedure:

1. Install the secondary card in any free PCIe slot (x1 electrical is fine
   for display).
2. Plug the monitor(s) into the secondary card.
3. Boot. Both vendors' drivers coexist on Win11.
4. In Windows Settings → Display → Graphics, set the 3090 as "High
   performance" GPU. CUDA, NVENC, and games target the 3090 automatically
   because nothing else has a CUDA runtime.
5. `nvidia-smi` should show GPU0 (the 3090) at <1 GiB at idle.

This is the most reliable single-GPU rescue on Windows. Many local-LLM
users on r/LocalLLaMA report 2-3 GiB reclaimed and noticeably more stable
KV-cache headroom.

Driver notes:

- **NVIDIA + NVIDIA** (e.g., GT 1030 + RTX 3090): only one NVIDIA driver
  package can be installed system-wide and it must support both
  architectures. Current 560+ drivers cover Pascal through Ada in one
  package, so GT 1030 + 3090 is fine today. The day NVIDIA drops Pascal,
  GT 1030 will throw a Code 31 in Device Manager — at that point swap
  to a Turing+ low-end card (GTX 1650).
- **NVIDIA + AMD** (e.g., RX 6400 + RTX 3090) is architecturally cleaner:
  separate driver packages, no version-lock risk, and the AMD card
  fully owns the display compositor. Win11 23H2 / 24H2 handle this well.
  Set `CUDA_VISIBLE_DEVICES` to point only at the 3090 to avoid stray
  enumeration of the GT 1030 if you go the NV+NV route.
- After installing the second card, a clean reinstall of the NVIDIA
  driver via DDU (display driver only, no GeForce Experience / NVIDIA
  App) reduces the chance of the well-known "one of two NVIDIA cards
  randomly disabled" bug some users hit on Win11.

### 3. Disable hardware acceleration in apps — ~1-3 GiB freed, free, 5 minutes

This is the highest leverage knob if you skip everything else. Per-app
toggles:

- **Chrome / Edge / Brave / Vivaldi**: Settings → System → "Use graphics
  acceleration when available" → **Off**. Restart the browser. Saves
  ~600 MiB-1.5 GiB depending on tab count.
- **Microsoft Teams**: Settings → General → "Disable GPU hardware
  acceleration" → **On**. Saves ~300-600 MiB.
- **Discord**: User Settings → Advanced → "Hardware Acceleration" → **Off**.
  Saves ~200-400 MiB.
- **Microsoft Office (Word/Excel/Outlook)**: File → Options → Advanced →
  Display → "Disable hardware graphics acceleration" → **On**. Saves
  ~150-300 MiB across the suite.
- **VS Code**: command palette → "Disable GPU Acceleration" (or launch
  with `--disable-gpu`). Saves ~200-400 MiB.
- **Slack**: similar toggle in Advanced settings.
- **Spotify**: Settings → Display → "Hardware acceleration" off.

Cumulative on a typical office desktop: 1.5-2.5 GiB. Tradeoff is slightly
laggier scrolling and CPU-decoded video. For an LLM workstation, easy win.

### 4. Close everything before launching vLLM — ~2-4 GiB freed, free

Crude but works. A `start_vllm.bat` that does this before launching the
server:

```batch
taskkill /F /IM chrome.exe   2>nul
taskkill /F /IM msedge.exe   2>nul
taskkill /F /IM Teams.exe    2>nul
taskkill /F /IM Outlook.exe  2>nul
taskkill /F /IM Discord.exe  2>nul
taskkill /F /IM SnagitEditor.exe 2>nul
taskkill /F /IM Snagit32.exe 2>nul
timeout /t 2 /nobreak >nul
nvidia-smi --query-gpu=memory.free --format=csv
```

Combined with #3, this comfortably reclaims 4-6 GiB on a busy desktop.

### 5. RDP / `tscon` console disconnect — ~0-0.5 GiB, situational

Disconnecting the local console session via `tscon` (move the session to
a "listener") is a known trick on Windows Server. On Windows 10/11
Pro/Enterprise it partially works: DWM for the local session goes idle but
the framebuffer stays mapped. Real-world VRAM savings are small (under
500 MiB) and apps that respond to session-change events (Teams, OneDrive)
may misbehave. Not worth the friction unless you already RDP in daily.

### 6. Hardware-accelerated GPU scheduling (HAGS) — neutral

Settings → System → Display → Graphics → Default settings → "Hardware-
accelerated GPU scheduling" toggle. Reports are mixed:

- **On**: marginally lower latency for games, sometimes a tiny bit less
  VRAM allocated to DWM staging buffers. CUDA workloads neutral.
- **Off**: more predictable behaviour for very long-running CUDA kernels;
  some users report fewer "GPU TDR" hangs under sustained vLLM load.

For vLLM specifically, leave it at the default (On for Win11) unless you
hit TDR resets, in which case try Off.

### 7. Increase TDR delay — doesn't free VRAM but prevents crashes

Long prefill on a busy GPU can hit Windows' default 2-second timeout. Add
under `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers`:

```
TdrDelay     (DWORD) = 60
TdrDdiDelay  (DWORD) = 60
```

Reboot. Not a VRAM workaround per se, but the symptom of "vLLM dies during
long prefills on the display GPU" is sometimes a TDR, not OOM.

### 8. Lower vLLM `--gpu-memory-utilization` and `--max-model-len` — always works

The reliable fallback. On a display-attached 24 GiB 3090 running Qwen3-27B
INT4, sane starting points:

- `--gpu-memory-utilization 0.82`
- `--max-model-len 32768` (drop to 16384 if you OOM during long-context
  prefill)
- `--enforce-eager` if you have <2 GiB headroom and CUDA graphs OOM.

This trades context length for fitting at all. See this repo's
`start_gpu0_50k` and similar snapshots for tuned profiles.

## What does NOT work / is no longer possible

### TCC mode on consumer GeForce — dead, and has been for years

NVIDIA has restricted TCC (Tesla Compute Cluster) mode to professional and
data-center SKUs since the Turing generation. On RTX 30/40/50 series the
`nvidia-smi -dm 1` command returns "feature not supported on this GPU"
regardless of driver version. This was confirmed across 470, 535, 550, and
560-series drivers and there is no community-known driver hack as of late
2025. The "modded driver" tricks that worked on early Pascal are dead.

If you need a card you can flip to TCC, your options are RTX A4000 / A5000
/ A6000, the L4/L40, or older Quadros (RTX 4000/5000/6000 of the Turing
generation). All cost meaningfully more than a used 3090.

### Disabling DWM permanently — not supported

You can `Stop-Service uxsms` but Session Manager respawns DWM. Registry
hacks that worked on Windows 7 (`DisableDWM`) have no effect on 10/11.
There is no supported "no-compositor" mode.

### WSL2 to free Windows VRAM — does not work

WSL2's CUDA support is GPU-PV (paravirtualized), which means the Windows
host driver still owns the GPU, and DWM is still running on the host. VRAM
is shared, not reassigned. Running vLLM inside WSL2 on a single-GPU box
gives you:

- the same Windows desktop tax as before,
- plus a small overhead for the GPU-PV abstraction,
- minus some Windows-specific bugs (NCCL, some kernel ABI issues).

WSL2 is the right answer for "I need Linux-only Python tooling," not for
"I need more VRAM." Run vLLM natively on Windows (this project) or
dual-boot Linux for real headless.

### Hyper-V DDA / GPU partitioning on Win11 Pro — not for this use case

Hyper-V Discrete Device Assignment requires Windows Server, not Win11 Pro.
GPU Partitioning (GPU-P) on Win11 Pro is gated to specific OEM scenarios
(WSLg, some Xbox Cloud configs) and is not exposed for general VM use.
Proxmox / KVM passthrough on Linux is the working alternative, but at that
point you are running Linux and the question is moot.

### Killing `dwm.exe` to free VRAM — temporary at best

`taskkill /F /IM dwm.exe` works for ~1 second before the Session Manager
restarts it. There is no supported way to keep it dead while a user
session is active. Even if you could, individual apps (Edge, Teams) hold
their own GPU contexts that are unaffected by DWM.

### Removing display drivers with DDU and not reinstalling — breaks CUDA

The CUDA runtime on Windows depends on the same display driver. There is
no separate "compute-only" driver package for GeForce. If you uninstall
the display driver, CUDA stops working too.

## Decision tree

```
1× 24 GB GPU, display attached, AMD CPU (no iGPU)
  └─ Best:  add a $60 GT 1030 for display, leave 3090 compute-only
  └─ Free:  disable HW accel in Chrome/Teams/Office (#3) + close apps (#4)
            then start_gpu0 profile, expect 16-32k context for 27B INT4.

1× 24 GB GPU, display attached, Intel CPU with UHD 770
  └─ Best:  route display to iGPU in BIOS + Windows graphics settings (#1).
            Free, ~3 GiB reclaimed.

1× 32 GB GPU (RTX 5090), display attached
  └─ Comfortable. 27B INT4 fits with full context even with the desktop tax.
            Apply #3 anyway, run start_speed profile.

1× 16 GB GPU (4060 Ti / 4070 Ti Super), display attached
  └─ Tight for 27B INT4. Either step down to 14B INT4, or aggressively apply
            #1 or #2 plus #3+#4. Do NOT expect long context.

2× dGPUs (this project's reference setup)
  └─ Display on GPU0, vLLM on GPU1 with `CUDA_VISIBLE_DEVICES=1`.
            Or PP=2 / TP=2 across both — see the project's PP/TP memory.

iGPU + 1× dGPU
  └─ Pin display to iGPU. dGPU runs vLLM full-fat. Identical to #1.

Want truly headless like Linux
  └─ Dual-boot Linux, or repurpose an old box as a Linux inference server.
            No supported Windows path gets you there on consumer GeForce.
```

## Sources

Research conducted late April 2026 against Reddit (r/LocalLLaMA, r/nvidia,
r/buildapc), NVIDIA developer forums, Microsoft Learn, and Perplexity
synthesised search. Key threads consulted:

- NVIDIA dev forum: "TCC mode on RTX 4090?" — repeated NVIDIA staff
  confirmation that TCC is not supported on GeForce, multiple driver
  generations.
- r/LocalLLaMA: many threads on "free up VRAM on display GPU Windows" all
  converging on the iGPU / second-GPU recommendation.
- Microsoft Learn: WDDM driver model docs confirming framebuffer
  reservation while a display device is enumerated.
- WSL CUDA docs (docs.nvidia.com / learn.microsoft.com): GPU-PV
  architecture explanation confirming shared host GPU.
- r/nvidia threads on `dwm.exe` respawn behavior post-Win10 1903.
- Multiple build threads on r/buildapc confirming GT 1030 / RX 6400 as
  display-only secondary cards alongside a 3090/4090 with no driver
  conflicts on Win11 23H2 / 24H2.

If you find a workaround not listed here that actually moves the needle,
please open an issue on `devnen/vllm-windows` with `nvidia-smi` before/
after numbers and the exact OS build / driver version.

# Credits

This fork is a thin layer on top of a tall stack of other people's work.

## Upstream projects

- **[vLLM](https://github.com/vllm-project/vllm)** — the engine. Apache-2.0.
  This fork follows their license. Source: `vllm/`.
- **[SystemPanic/vllm-windows](https://github.com/SystemPanic/vllm-windows)** —
  the Windows wheel build infrastructure and CUDA-12.6 / PyTorch 2.11.0
  base this fork is built against. Without their multi-day MSVC/CUDA
  toolchain wrangling, native vLLM on Windows wouldn't exist at all.
- **[Lorbus](https://huggingface.co/Lorbus)** — produced
  [`Qwen3.6-27B-int4-AutoRound`](https://huggingface.co/Lorbus/Qwen3.6-27B-int4-AutoRound),
  the only 27B INT4 quant we know of that keeps the MTP head in BF16.
  Without that, MTP spec-decode silently no-ops on 27B and the speed
  numbers in this README don't exist.
- **[Qwen team](https://huggingface.co/Qwen)** — Qwen3.6-27B base model.

## Patches we mirror

- **PR [#35687](https://github.com/vllm-project/vllm/pull/35687)** — the
  Qwen3 reasoning parser fix that treats `<tool_call>` as an implicit
  `</think>`. Mirrored verbatim into our `qwen3_reasoning_parser.py`.

## Tools

- **[Textual](https://github.com/Textualize/textual)** — the TUI framework
  the launcher is built on. The portable launcher's footprint is dominated
  by Textual + Rich + their dependencies.
- **[httpx](https://github.com/encode/httpx)** — async HTTP client used by
  the launcher's bench/test path.

## Community signal

The configurations and tradeoffs in this fork were shaped by recipes,
benchmarks, and hard-won failure stories from r/LocalLLaMA — particularly
the people who dared post their numbers and let the community tear them
apart. Specific threads we leaned on are linked from the relevant docs.

If your work is here and you'd like a more direct attribution, please open
an issue.

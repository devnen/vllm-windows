"""Benchmark prefill+decode by summarizing a long Python source file.

Reports prefill tok/s (prompt_tokens / TTFT), decode tok/s, wall tok/s, prompt
length, KV pool size (read from the matching log file if present), plus the
active config string passed in via --label. Appends a TSV row to ``runs.tsv``
so configs can be diffed at a glance.

Default prompt source: ``windows_tools/bench_prompt_sample.py`` (vendored
public-domain inspect.py from CPython, pruned to ~24 k tokens). Override via
``--code <path>`` if you want to bench a different long input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import bench  # local

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CODE_PATH = Path(__file__).resolve().parent / "bench_prompt_sample.py"

def _log_path_for(port: int) -> Path:
    base = Path(os.environ.get("VLLM_WINDOWS_LOGS", str(REPO / "logs")))
    return base / f"vllm_server.{port}.log"

RUNS_TSV = REPO / "runs.tsv"

PROMPT_TEMPLATE = (
    "Summarize this Python service module in 8 bullet points: top-level purpose, "
    "key classes, public entry points, threading/async model, side effects, "
    "external deps, error handling style, anything unusual. Be terse.\n\n"
    "/no_think\n\n"
    "```python\n{code}\n```\n"
)


def read_kv_pool(port: int) -> int | None:
    log_path = _log_path_for(port)
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = re.findall(r"GPU KV cache size:\s*([\d,]+)\s*tokens", text)
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True, help="Short config tag, e.g. ctx65k_mem095")
    p.add_argument("--max-tokens", type=int, default=200)
    p.add_argument("--base", default=bench.BASE)
    p.add_argument("--wait", type=int, default=600, help="Seconds to wait for server")
    p.add_argument("--code", default=str(DEFAULT_CODE_PATH), help="Path to source file to summarize")
    a = p.parse_args()

    bench.BASE = a.base
    bench.wait_ready(a.wait)

    code_path = Path(a.code)
    code = code_path.read_text(encoding="utf-8", errors="replace")
    prompt = PROMPT_TEMPLATE.format(code=code)
    print(f"[bench] prompt chars: {len(prompt):,}  (file {code_path.name}: {len(code):,} chars)")

    res = bench.bench(prompt, max_tokens=a.max_tokens, quiet=True)
    # parse port from base url for log lookup
    try:
        port = int(a.base.rsplit(":", 1)[-1].split("/", 1)[0])
    except ValueError:
        port = 5001
    pool = read_kv_pool(port)

    pt = res.get("prompt_tokens") or 0
    ttft = res.get("TTFT_s") or 0.0
    prefill_tps = round(pt / ttft, 1) if pt and ttft else None

    row = {
        "label": a.label,
        "kv_pool_tokens": pool,
        "prompt_tokens": pt,
        "completion_tokens": res.get("completion_tokens"),
        "TTFT_s": ttft,
        "prefill_tok_s": prefill_tps,
        "decode_tok_s": res.get("decode_tok_s"),
        "wall_tok_s": res.get("wall_tok_s"),
        "wall_s": res.get("wall_s"),
    }

    print("\n--- bench_summarize ---")
    for k, v in row.items():
        print(f"  {k:20s}: {v}")

    headers = list(row.keys())
    write_header = not RUNS_TSV.exists()
    with RUNS_TSV.open("a", encoding="utf-8") as f:
        if write_header:
            f.write("\t".join(headers) + "\n")
        f.write("\t".join("" if row[k] is None else str(row[k]) for k in headers) + "\n")
    print(f"[bench] appended row to {RUNS_TSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

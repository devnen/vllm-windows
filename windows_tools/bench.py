"""Streaming tok/s benchmark against the local vllm-turbo server.

Reports:
  TTFT         - seconds to first generated token (prefill cost)
  decode tok/s - tokens-per-second during the streaming phase only (excludes
                 prefill); matches what the article calls "sustained TPS"
  wall tok/s   - total completion_tokens / total seconds (prefill + decode)
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

import os
BASE = os.environ.get("VLLM_BENCH_BASE", "http://127.0.0.1:5001")
MODEL = os.environ.get("VLLM_BENCH_MODEL", "any")

DEFAULT_PROMPT = (
    "Write a 300-word plain-text explanation of how transformer attention "
    "works. No lists, no code, no markdown. Single flowing prose."
)


def wait_ready(timeout_s: int = 900) -> None:
    url = f"{BASE}/v1/models"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(3)
    raise SystemExit(f"Server not ready within {timeout_s}s at {BASE}")


def bench(prompt: str, max_tokens: int, quiet: bool) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    t0 = time.perf_counter()
    t_first = None
    n_chunks = 0
    usage = None
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            for choice in obj.get("choices", []):
                delta = choice.get("delta", {}) or {}
                piece = (
                    delta.get("content")
                    or delta.get("reasoning")
                    or delta.get("reasoning_content")
                    or ""
                )
                if piece:
                    if t_first is None:
                        t_first = time.perf_counter()
                    n_chunks += 1
                    if not quiet:
                        print(piece, end="", flush=True)
    t_end = time.perf_counter()
    if not quiet:
        print()

    total = t_end - t0
    ttft = (t_first - t0) if t_first else float("nan")
    decode_window = (t_end - t_first) if t_first else float("nan")
    completion_tokens = (usage or {}).get("completion_tokens") or n_chunks
    prompt_tokens = (usage or {}).get("prompt_tokens")

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "wall_s": round(total, 2),
        "TTFT_s": round(ttft, 3),
        "decode_window_s": round(decode_window, 3),
        "decode_tok_s": round(completion_tokens / decode_window, 2) if decode_window and decode_window > 0 else None,
        "wall_tok_s": round(completion_tokens / total, 2),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--max-tokens", type=int, default=300)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--wait", action="store_true", help="Block until server ready.")
    a = p.parse_args()
    if a.wait:
        wait_ready()
    res = bench(a.prompt, a.max_tokens, a.quiet)
    print("\n--- benchmark ---")
    for k, v in res.items():
        print(f"{k:18s}: {v}")


if __name__ == "__main__":
    main()

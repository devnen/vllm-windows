"""Client-side tok/s benchmark against the popos vLLM server.

Streams a chat completion, measures:
  - TTFT: time to first chunk (proxy for prefill latency)
  - decode tok/s: chunks/second during the streaming phase
  - total tok/s
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

DEFAULT_URL = "http://192.168.1.116:5000/v1/chat/completions"
DEFAULT_MODEL = "qwen3.6-27b"
DEFAULT_PROMPT = (
    "Write a detailed 300-word explanation of how transformer attention works. "
    "Use plain prose, no lists."
)


def run(url: str, model: str, prompt: str, max_tokens: int) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t_sent = time.perf_counter()
    t_first = None
    t_last = t_sent
    chunks = 0
    usage = None
    content = []

    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            body = line[len("data:"):].strip()
            if body == "[DONE]":
                break
            try:
                obj = json.loads(body)
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
                    t_last = time.perf_counter()
                    chunks += 1
                    content.append(piece)

    t_total = t_last - t_sent
    ttft = (t_first - t_sent) if t_first else None
    decode_elapsed = (t_last - t_first) if t_first else 0.0
    decode_toks = (usage or {}).get("completion_tokens", chunks)
    prompt_toks = (usage or {}).get("prompt_tokens", -1)

    print("--- benchmark ---")
    print(f"prompt_tokens     : {prompt_toks}")
    print(f"completion_tokens : {decode_toks}")
    print(f"chunks_received   : {chunks}")
    print(f"total_elapsed_s   : {t_total:.2f}")
    print(f"TTFT_s            : {ttft:.2f}" if ttft else "TTFT_s            : n/a")
    print(f"decode_window_s   : {decode_elapsed:.2f}")
    if decode_elapsed > 0:
        print(f"decode tok/s      : {decode_toks / decode_elapsed:.2f}")
    if t_total > 0:
        print(f"wall tok/s        : {decode_toks / t_total:.2f}")
    print("--- output preview ---")
    full = "".join(content)
    print(full[:400] + ("..." if len(full) > 400 else ""))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--max-tokens", type=int, default=300)
    args = p.parse_args()
    run(args.url, args.model, args.prompt, args.max_tokens)


if __name__ == "__main__":
    main()

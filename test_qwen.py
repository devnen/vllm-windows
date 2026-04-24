"""Streaming inference smoke test for qwen3.6-27b served by local vLLM.

Qwen3 is a thinking model — the stream may include <think>...</think> tags
and/or fill `reasoning_content` on the OpenAI delta. We print reasoning dim
and the answer in the default color so the split is visible.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:5000"
MODEL = "qwen3.6-27b"
PROMPT = (
    "Three boxes contain fruit. One has only apples, one only oranges, one "
    "both. All three labels are wrong. You may draw one fruit from one box. "
    "How do you correctly label all three? Answer concisely."
)

RESET, DIM, CYAN = "\x1b[0m", "\x1b[2m", "\x1b[36m"


def wait_ready(timeout_s: int = 600) -> None:
    url = f"{BASE}/v1/models"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"Server not ready within {timeout_s}s at {BASE}")


def stream_chat(prompt: str) -> None:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 2048,
        "temperature": 0.6,
        "top_p": 0.95,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    print(f"{CYAN}PROMPT:{RESET} {prompt}\n")
    print(f"{CYAN}STREAM:{RESET}")

    t0 = time.time()
    n_tokens = 0
    in_think = False
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                msg = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = msg.get("choices", [{}])[0].get("delta", {}) or {}

            # Separate channel for reasoning (qwen3 parser emits it here)
            r_chunk = delta.get("reasoning_content") or ""
            if r_chunk:
                if not in_think:
                    sys.stdout.write(f"{DIM}[think] ")
                    in_think = True
                sys.stdout.write(f"{DIM}{r_chunk}{RESET}")
                sys.stdout.flush()
                n_tokens += 1

            # Answer content
            c_chunk = delta.get("content") or ""
            if c_chunk:
                if in_think:
                    sys.stdout.write(f"{RESET}\n[/think]\n")
                    in_think = False
                sys.stdout.write(c_chunk)
                sys.stdout.flush()
                n_tokens += 1

    dt = time.time() - t0
    print(f"\n\n{CYAN}Done.{RESET} {n_tokens} delta events in {dt:.1f}s "
          f"({n_tokens / dt:.1f}/s)")


if __name__ == "__main__":
    print("Waiting for server readiness...")
    wait_ready()
    stream_chat(PROMPT)

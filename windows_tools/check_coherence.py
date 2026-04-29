"""Three-tier coherence check for a running vLLM server.

A degenerate config (wrong KV-dtype, wrong quantization flag, corrupt weights)
will cheerfully report 60+ tok/s while emitting ``* * * *`` or ``the the the``.
TPS without coherence is a lie. This script catches that before you ship.

Tests:
  1. Short-answer sanity   — "Capital of France?" (200 tok)
  2. Long-form narrative   — Whiskers cat / rooftop garden (700 tok)
  3. Code generation       — Iterative Fibonacci with docstring (500 tok)

Detects degenerate-attractor patterns: ``* * * *``, ``the the the``,
``**:**:**``, ``\\n\\n\\n\\n``, mid-sentence collapse to a 1–2 token loop.

Exit code 0 = all coherent. 1 = at least one degenerate. 2 = server unreachable.

Usage:
    python windows_tools/check_coherence.py --port 5001
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import urllib.error

DEGENERATE_PATTERNS = [
    (r"(\*\s*){5,}",                        "asterisk attractor"),
    (r"(\bthe\s+){5,}",                     "the-the-the loop"),
    (r"(\ba\s+){5,}",                       "a-a-a loop"),
    (r"(\*\*:){3,}",                        "delimiter loop"),
    (r"\n{6,}",                             "newline loop"),
    (r"(\b\w+\b\s+)\1{4,}",                 "single-token loop"),
]


def ask(port: int, prompt: str, max_tokens: int, model: str = "any", host: str = "127.0.0.1") -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "top_p": 0.9,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        obj = json.loads(r.read().decode("utf-8"))
    msg = obj["choices"][0]["message"]
    return (msg.get("content") or msg.get("reasoning") or "").strip()


def grade(label: str, text: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not text:
        issues.append("empty response")
    for pat, name in DEGENERATE_PATTERNS:
        if re.search(pat, text):
            issues.append(name)
    return (len(issues) == 0), issues


TIERS = [
    ("capital",   "What is the capital of France? Answer in one sentence.",                      200),
    ("whiskers",  "Write a 300-word story about a cat named Whiskers exploring a rooftop garden.", 700),
    ("fibonacci", "Write a Python function to compute the nth Fibonacci number iteratively, with a one-line docstring.", 500),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default="any")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    all_ok = True
    for label, prompt, n in TIERS:
        if not args.quiet:
            print(f"[{label}] asking ({n} tok)... ", end="", flush=True)
        try:
            text = ask(args.port, prompt, n, args.model, args.host)
        except urllib.error.URLError as e:
            print(f"\n[error] cannot reach http://{args.host}:{args.port} — {e}", file=sys.stderr)
            return 2
        ok, issues = grade(label, text)
        if not args.quiet:
            print("OK" if ok else f"FAIL ({', '.join(issues)})")
            print(f"  preview: {text[:200]!r}")
        if not ok:
            all_ok = False

    print("\nCOHERENT" if all_ok else "\nDEGENERATE — do not trust TPS numbers from this config.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

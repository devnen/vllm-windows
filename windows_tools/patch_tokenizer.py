"""Patch a Lorbus AutoRound tokenizer_config.json so transformers loads it.

Lorbus ships ``tokenizer_class: TokenizersBackend`` which transformers 4.57
on Windows does not recognize (raises ValueError at engine boot). The fix is
to switch it to ``Qwen2Tokenizer``. This script makes the change idempotent
and preserves a ``.bak`` so re-downloads don't lose your patched copy
silently — re-run after every fresh download.

Usage:
    python windows_tools/patch_tokenizer.py G:\\_models\\Qwen3.6-27B-int4-AutoRound
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir", help="path to the model directory containing tokenizer_config.json")
    args = ap.parse_args()

    md = Path(args.model_dir)
    cfg = md / "tokenizer_config.json"
    if not cfg.exists():
        print(f"[patch_tokenizer] no tokenizer_config.json at {cfg}", file=sys.stderr)
        return 1

    data = json.loads(cfg.read_text(encoding="utf-8"))
    cur = data.get("tokenizer_class")
    if cur == "Qwen2Tokenizer":
        print(f"[patch_tokenizer] already patched ({cur}); nothing to do.")
        return 0

    bak = cfg.with_suffix(".json.bak")
    if not bak.exists():
        shutil.copy2(cfg, bak)
        print(f"[patch_tokenizer] backed up to {bak.name}")

    data["tokenizer_class"] = "Qwen2Tokenizer"
    cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[patch_tokenizer] {cur!r} -> 'Qwen2Tokenizer' in {cfg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

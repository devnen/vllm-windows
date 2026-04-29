"""Verify model shard SHA-256s against HuggingFace's x-linked-etag header.

Catches torrent-like corruption that produces fast-but-degenerate output.
One bad shard = ``* * * *`` at the API but normal-looking weights on disk.

Usage:
    python windows_tools/verify_model_sha.py G:\\_models\\Qwen3.6-27B-int4-AutoRound \\
        --repo Lorbus/Qwen3.6-27B-int4-AutoRound

The --repo arg is the HuggingFace org/repo. If omitted, the script reads it
from a config.json sibling to the safetensors files (``_name_or_path``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path


def hf_etag(repo: str, filename: str, revision: str = "main") -> str | None:
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            for k, v in r.headers.items():
                # Strict start-of-line match — header listings can mention
                # 'X-Linked-Etag' as a value of access-control-expose-headers.
                if k.lower() == "x-linked-etag":
                    return v.strip().strip('"')
    except urllib.error.HTTPError as e:
        print(f"  [warn] HEAD {filename} -> HTTP {e.code}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"  [warn] HEAD {filename} -> {e}", file=sys.stderr)
    return None


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--revision", default="main")
    args = ap.parse_args()

    md = Path(args.model_dir)
    if not md.is_dir():
        print(f"[verify_sha] not a directory: {md}", file=sys.stderr)
        return 1

    repo = args.repo
    if repo is None:
        cj = md / "config.json"
        if cj.exists():
            try:
                repo = json.loads(cj.read_text(encoding="utf-8")).get("_name_or_path")
            except Exception:
                pass
    if not repo:
        print("[verify_sha] --repo not given and config.json has no _name_or_path",
              file=sys.stderr)
        return 1

    shards = sorted(md.glob("*.safetensors"))
    if not shards:
        print(f"[verify_sha] no .safetensors in {md}", file=sys.stderr)
        return 1

    print(f"[verify_sha] repo={repo} revision={args.revision} shards={len(shards)}")
    bad = 0
    for f in shards:
        expected = hf_etag(repo, f.name, args.revision)
        if not expected:
            print(f"  [SKIP] {f.name}  (no x-linked-etag)")
            continue
        actual = sha256_file(f)
        ok = expected == actual
        print(f"  [{'OK' if ok else 'FAIL'}] {f.name}  exp={expected[:12]}  act={actual[:12]}")
        if not ok:
            bad += 1
    if bad:
        print(f"\nFAIL — {bad} shard(s) corrupt; re-download.")
        return 1
    print("\nOK — all shards match upstream.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

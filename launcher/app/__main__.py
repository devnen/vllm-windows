from __future__ import annotations
import argparse
import sys
from .app import LauncherApp


def main() -> None:
    p = argparse.ArgumentParser(prog="vllm_launcher", description="vLLM config launcher TUI")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="Run web UI only (textual-serve)")
    s.add_argument("--host", default="localhost")
    s.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    if args.cmd == "serve":
        from textual_serve.server import Server
        cmd = f'"{sys.executable}" -m vllm_launcher'
        Server(command=cmd, host=args.host, port=args.port, title="vLLM Launcher").serve()
        return

    LauncherApp().run()


if __name__ == "__main__":
    main()

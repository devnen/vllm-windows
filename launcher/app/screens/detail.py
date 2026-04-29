from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen, ModalScreen
from textual.widgets import Header, Footer, Static, Button

from ..config import WinConfig


class ConfirmModal(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    #box {
        background: #161b22;
        border: solid #f85149;
        padding: 1 3;
        width: 60;
        height: auto;
    }
    #box Button { margin: 1 1 0 0; }
    """

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(self.message)
            with Horizontal():
                yield Button("Confirm", id="ok", variant="error")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "ok")


class ResultModal(ModalScreen[None]):
    DEFAULT_CSS = """
    ResultModal { align: center middle; }
    #box {
        background: #161b22;
        border: solid #58a6ff;
        padding: 1 2;
        width: 90;
        height: auto;
        max-height: 80%;
    }
    """

    def __init__(self, title: str, body: str):
        super().__init__()
        self.title_str = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(f"[b #58a6ff]{self.title_str}[/]\n")
            yield Static(self.body)
            yield Button("Close", id="close")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(None)


def _kv(rows: list[tuple[str, str]]) -> str:
    out: list[str] = []
    for k, v in rows:
        out.append(f" [#8b949e]{k:<13}[/] [#e6edf3]{v}[/]")
    return "\n".join(out)


class DetailScreen(Screen):
    DEFAULT_CSS = """
    DetailScreen { background: #0d1117; color: #e6edf3; layout: vertical; }
    #cols { height: 1fr; }
    #left, #right {
        background: #161b22;
        border: solid #30363d;
        padding: 0 1;
        width: 1fr;
        margin: 1 1 0 1;
    }
    #right { color: #8b949e; }
    #actions {
        height: 4;
        padding: 0 2;
        margin: 0;
        background: #11161d;
        border-top: solid #30363d;
    }
    #actions Button {
        margin: 0 1 0 0;
        min-width: 14;
        height: 3;
        content-align: center middle;
    }
    #actions Button#back-btn {
        background: #21262d;
    }
    .running-banner {
        background: #11202f;
        border-left: thick #3fb950;
        padding: 0 2;
        color: #3fb950;
        text-style: bold;
        height: 1;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back"),
        ("l", "load", "Load"),
        ("u", "unload", "Unload"),
        ("t", "test", "Test"),
    ]

    def __init__(self, cfg: WinConfig, bundle, **kw):
        super().__init__(**kw)
        self.cfg = cfg
        self.bundle = bundle

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        cfg = self.cfg
        is_running = cfg.id in self.app.running_ids

        if is_running:
            yield Static(f"  ● RUNNING — port {cfg.port}", classes="running-banner")

        with Horizontal(id="cols"):
            with VerticalScroll(id="left"):
                yield Static(self._meta_text())
            with VerticalScroll(id="right"):
                yield Static(self._right_text())

        with Horizontal(id="actions"):
            yield Button("Load (L)", id="load-btn", variant="success",
                         disabled=(cfg.status == "blocked"))
            yield Button("Unload (U)", id="unload-btn", variant="error",
                         disabled=not is_running)
            yield Button("Test (T)", id="test-btn", variant="primary",
                         disabled=not is_running)
            yield Button("Back (Esc)", id="back-btn")
        yield Footer()

    def _meta_text(self) -> str:
        cfg = self.cfg
        sd = self.bundle.shared_defaults
        meta_rows = [
            ("ID", cfg.id),
            ("Tagline", cfg.tagline),
            ("Tier / Status", f"{cfg.tier} / {cfg.status}"),
            ("Bat", cfg.bat),
            ("Py", cfg.py),
            ("GPU", cfg.gpu),
            ("TP × PP", f"{cfg.tp} × {cfg.pp}"),
            ("mem-util", f"{cfg.mem_util}"),
            ("ctx (max-model-len)", f"{cfg.ctx:,}"),
            ("port", str(cfg.port)),
            ("MTP n", "—" if cfg.mtp_n is None else str(cfg.mtp_n)),
            ("draft-model n", "—" if cfg.draft_model_n is None else str(cfg.draft_model_n)),
            ("Power cap", f"{cfg.power_cap_w or sd.get('power_cap_w', '?')} W"),
        ]
        shared_rows = [
            (k, str(sd[k])) for k in [
                "model_path", "served_model_name", "quantization", "kv_cache_dtype",
                "attention_backend", "vllm_version", "max_num_seqs",
                "max_num_batched_tokens", "block_size",
            ] if k in sd
        ]
        return (
            f"[b #58a6ff]Config metadata[/]\n"
            f"{_kv(meta_rows)}\n\n"
            f"[b #58a6ff]Shared defaults[/]\n"
            f"{_kv(shared_rows)}"
        )

    def _right_text(self) -> str:
        cfg = self.cfg
        bench_rows: list[tuple[str, str]] = []
        for k, v in [
            ("decode_tps (24k prompt)", cfg.decode_tps),
            ("decode_tps (short)", cfg.decode_tps_short),
            ("decode_tps (long)", cfg.decode_tps_long),
            ("prefill cold tok/s", cfg.prefill_tps_cold),
        ]:
            if v is not None:
                bench_rows.append((k, str(v)))
        bench = _kv(bench_rows) if bench_rows else "  [#8b949e]—[/]"

        sweep_lines: list[str] = []
        for r in self.bundle.mtp_sweep.get("rows", []):
            mark = " [b #ffbb7f]★ peak[/]" if r.get("peak") else ""
            sweep_lines.append(
                f"  [#8b949e]n={r['mtp_n']}[/]   [#e6edf3]ctx={r['ctx']//1000:>4}k[/]   "
                f"[#3fb950]{r['decode_tps']:>5} t/s[/]{mark}"
            )

        notes = (cfg.notes or "—").rstrip()

        return (
            f"[b #58a6ff]Benchmarks[/]\n"
            f"{bench}\n\n"
            f"[b #58a6ff]Notes[/]\n"
            f" [#8b949e]{notes}[/]\n\n"
            f"[b #58a6ff]MTP sweep (speed config baseline)[/]\n"
            + "\n".join(sweep_lines)
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_load(self) -> None:
        self._do_load()

    def action_unload(self) -> None:
        self._do_unload()

    def action_test(self) -> None:
        self._do_test()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "back-btn":
            self.action_back()
        elif ev.button.id == "load-btn":
            self._do_load()
        elif ev.button.id == "unload-btn":
            self._do_unload()
        elif ev.button.id == "test-btn":
            self._do_test()

    def _do_load(self) -> None:
        cfg = self.cfg
        def _yes(ok: bool):
            if ok:
                from .. import runtime
                try:
                    runtime.start_config(cfg.bat, cfg.id)
                    self.app.notify(f"Launched {cfg.id} in Windows Terminal", timeout=4)
                except Exception as e:
                    self.app.notify(f"Launch failed: {e}", severity="error", timeout=6)
        self.app.push_screen(
            ConfirmModal(f"Launch {cfg.id} ({cfg.bat})?\nA new console window will open."),
            _yes,
        )

    def _do_unload(self) -> None:
        cfg = self.cfg
        proc = self.app.running.get(cfg.id)
        if not proc:
            self.app.notify("Not running", severity="warning"); return
        def _yes(ok: bool):
            if ok:
                from .. import runtime
                success, msg = runtime.kill_pid(proc.pid)
                self.app.notify(("Killed " if success else "Kill failed: ") + msg,
                               severity="information" if success else "error", timeout=6)
                self.app.refresh_running()
        self.app.push_screen(
            ConfirmModal(f"Kill PID {proc.pid} on port {proc.port}?\nThis stops vLLM."),
            _yes,
        )

    def _do_test(self) -> None:
        cfg = self.cfg
        port = cfg.port
        served = self.bundle.shared_defaults.get("served_model_name", "qwen3.6-27b-autoround")
        self.app.notify("Testing inference...", timeout=2)
        self.app.run_worker(
            lambda: self._test_blocking(port, served),
            thread=True, exclusive=True,
        )

    def _test_blocking(self, port: int, served: str) -> None:
        from .. import inference
        result = inference.test_chat(port, model=served)
        if not result.get("ok"):
            self.app.call_from_thread(
                self.app.push_screen,
                ResultModal("Test failed", f"[#f85149]{result.get('error','?')}[/]"),
            )
            return
        body = (
            f"[b]Response:[/] {result['text']}\n\n"
            f"[#8b949e]prompt_tokens:[/] {result['prompt_tokens']}\n"
            f"[#8b949e]completion_tokens:[/] {result['completion_tokens']}\n"
            f"[#8b949e]TTFT:[/] {result['ttft_s']:.2f}s\n"
            f"[#8b949e]total:[/] {result['total_s']:.2f}s\n"
            f"[b #3fb950]decode tok/s: {result['decode_tps']:.1f}[/]"
        )
        self.app.call_from_thread(
            self.app.push_screen, ResultModal(f"Test → {self.cfg.id}", body)
        )

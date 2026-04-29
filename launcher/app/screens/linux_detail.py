from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Button

from ..config import LinuxConfig
from .detail import ConfirmModal, ResultModal, _kv


class LinuxDetailScreen(Screen):
    DEFAULT_CSS = """
    LinuxDetailScreen { background: #0d1117; color: #e6edf3; layout: vertical; }
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
    #actions Button#back-btn { background: #21262d; }
    .running-banner {
        background: #11202f;
        border-left: thick #3fb950;
        padding: 0 2;
        color: #3fb950;
        text-style: bold;
        height: 1;
    }
    .linux-banner {
        background: #2d220a;
        border-left: thick #d29922;
        padding: 0 2;
        color: #d29922;
        text-style: bold;
        height: 1;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back"),
        ("l", "load", "Load"),
        ("u", "unload", "Unload"),
        ("t", "test", "Test"),
        ("g", "log", "Log"),
    ]

    def __init__(self, cfg: LinuxConfig, bundle, **kw):
        super().__init__(**kw)
        self.cfg = cfg
        self.bundle = bundle

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        cfg = self.cfg
        is_running = cfg.id in self.app.linux_running_ids

        if is_running:
            yield Static(f"  ● RUNNING — {cfg.id} on popos:{cfg.port}", classes="running-banner")
        else:
            sd = self.bundle.linux_shared_defaults
            yield Static(
                f"  ◌ Linux popos — ssh {sd.get('ssh_user','?')}@{sd.get('ssh_host','?')}",
                classes="linux-banner",
            )

        with Horizontal(id="cols"):
            with VerticalScroll(id="left"):
                yield Static(self._meta_text())
            with VerticalScroll(id="right"):
                yield Static(self._right_text())

        with Horizontal(id="actions"):
            can_load = bool(cfg.launch_sh) and cfg.status != "blocked" and not is_running
            yield Button("Load (L)", id="load-btn", variant="success", disabled=not can_load)
            yield Button("Unload (U)", id="unload-btn", variant="error", disabled=not is_running)
            yield Button("Test (T)", id="test-btn", variant="primary", disabled=not is_running)
            yield Button("Log (G)", id="log-btn")
            yield Button("Back (Esc)", id="back-btn")
        yield Footer()

    def _meta_text(self) -> str:
        cfg = self.cfg
        sd = self.bundle.linux_shared_defaults
        meta_rows = [
            ("ID", cfg.id),
            ("Tagline", cfg.tagline),
            ("Tier / Status", f"{cfg.tier} / {cfg.status}"),
            ("Launch .sh", cfg.launch_sh or "[#f85149]— (no launcher script)[/]"),
            ("Config YAML", cfg.yaml_path),
            ("GPU", cfg.gpu),
            ("TP × PP", f"{cfg.tp} × {cfg.pp}"),
            ("mem-util", f"{cfg.mem_util}"),
            ("ctx (max-model-len)", f"{cfg.ctx:,}"),
            ("port", str(cfg.port)),
            ("KV dtype", cfg.kv_dtype),
            ("vision tower", "ON" if cfg.vision_on else "OFF (--language-model-only)"),
            ("MTP n", "—" if cfg.mtp_n is None else str(cfg.mtp_n)),
            ("draft-model n", "—" if cfg.draft_model_n is None else str(cfg.draft_model_n)),
            ("Container", f"vllm-qwen36-27b-turbo-{cfg.container}"),
            ("Power cap", f"{cfg.power_cap_w or sd.get('power_cap_w', '?')} W"),
        ]
        ssh_rows = [
            ("ssh host", sd.get("ssh_host", "?")),
            ("ssh user", sd.get("ssh_user", "?")),
            ("project_dir", sd.get("project_dir", "?")),
        ]
        shared_rows = [
            (k, str(sd[k])) for k in [
                "model_path", "served_model_name", "quantization",
                "attention_backend", "vllm_version", "max_num_seqs",
                "max_num_batched_tokens",
            ] if k in sd
        ]
        return (
            f"[b #58a6ff]Config metadata[/]\n"
            f"{_kv(meta_rows)}\n\n"
            f"[b #58a6ff]Remote host[/]\n"
            f"{_kv(ssh_rows)}\n\n"
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
        notes = (cfg.notes or "—").rstrip()

        actions_help = (
            "[b #58a6ff]Actions[/]\n"
            "  [#3fb950]Load (L)[/]    SSH → fire launch-*.sh in background\n"
            "                  (3-5 min boot for tp2; tail with [b]Log (G)[/])\n"
            "  [#f85149]Unload (U)[/]  SIGTERM the launch script (its trap runs\n"
            "                  docker compose down + nvidia-smi -pl 200)\n"
            "  [#58a6ff]Test (T)[/]    OpenAI /chat/completions to popos:5001\n"
            "  [#8b949e]Log (G)[/]    Tail /tmp/vllm-launcher-<id>.log\n"
        )
        return (
            f"[b #58a6ff]Benchmarks[/]\n"
            f"{bench}\n\n"
            f"[b #58a6ff]Notes[/]\n"
            f" [#8b949e]{notes}[/]\n\n"
            f"{actions_help}"
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_load(self) -> None: self._do_load()
    def action_unload(self) -> None: self._do_unload()
    def action_test(self) -> None: self._do_test()
    def action_log(self) -> None: self._do_log()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id
        if bid == "back-btn": self.action_back()
        elif bid == "load-btn": self._do_load()
        elif bid == "unload-btn": self._do_unload()
        elif bid == "test-btn": self._do_test()
        elif bid == "log-btn": self._do_log()

    def _ssh(self) -> tuple[str, str, str]:
        sd = self.bundle.linux_shared_defaults
        return sd["ssh_host"], sd["ssh_user"], sd["ssh_password"]

    def _do_load(self) -> None:
        cfg = self.cfg
        if not cfg.launch_sh:
            self.app.notify("No launch script for this config", severity="warning"); return

        # Case 1: this exact config is already running -> info popup, no action
        if cfg.id in self.app.linux_running_ids:
            self.app.push_screen(ResultModal(
                f"{cfg.id} already loaded",
                f"[b #3fb950]●[/] [b]{cfg.id}[/] is already running on popos:{cfg.port}.\n\n"
                f"  [#8b949e]tagline:[/] {cfg.tagline}\n"
                f"  [#8b949e]ctx:[/] {cfg.ctx:,}\n\n"
                f"Use [b #f85149]Unload[/] first if you want to relaunch it."
            ))
            return

        # Case 2: another linux config is running -> offer auto-unload-then-load chain
        others = sorted(x for x in self.app.linux_running_ids if x != cfg.id)
        if others:
            other_id = others[0]
            msg = (
                f"[b #d29922]Currently running:[/] {other_id}\n"
                f"Port 5001 is occupied. To load [b]{cfg.id}[/], the launcher will:\n"
                f"  1. Stop {other_id} (SIGTERM launch script → docker compose down)\n"
                f"  2. Wait for it to fully release port 5001\n"
                f"  3. Fire {cfg.launch_sh.rsplit('/', 1)[-1]}\n\n"
                f"Total time: ~5 minutes (boot + cudagraph capture).\n\n"
                f"Proceed?"
            )
            def _yes_chain(ok: bool):
                if not ok: return
                self.app.notify(f"Switching {other_id} → {cfg.id}...", timeout=4)
                self.app.run_worker(
                    lambda: self._unload_then_load_blocking(),
                    thread=True, exclusive=True,
                )
            self.app.push_screen(ConfirmModal(msg), _yes_chain)
            return

        # Case 3: nothing running -> straight load
        msg = (
            f"Launch {cfg.id} on popos?\n"
            f"  ssh → {cfg.launch_sh}\n"
            f"  Boot takes 3–5 minutes. Card flips to RUNNING when ready."
        )
        def _yes(ok: bool):
            if not ok: return
            self.app.notify(f"Launching {cfg.id} on popos...", timeout=4)
            self.app.run_worker(
                lambda: self._load_blocking(),
                thread=True, exclusive=True,
            )
        self.app.push_screen(ConfirmModal(msg), _yes)

    def _load_blocking(self) -> None:
        from .. import linux_runtime as lr
        host, user, pw = self._ssh()
        ok, msg = lr.start_config(host, user, pw, self.cfg)
        sev = "information" if ok else "error"
        self.app.call_from_thread(self.app.notify, msg, severity=sev, timeout=8)
        self.app.call_from_thread(self.app.refresh_linux_running)

    def _unload_then_load_blocking(self) -> None:
        """Stop whatever's running, wait for port release, then start self."""
        import time
        from .. import linux_runtime as lr
        host, user, pw = self._ssh()
        sd = self.bundle.linux_shared_defaults
        ok, msg = lr.stop_running(host, user, pw, sd)
        if not ok:
            self.app.call_from_thread(
                self.app.notify, f"Unload failed: {msg}", severity="error", timeout=8)
            return
        self.app.call_from_thread(
            self.app.notify, f"Unloaded ({msg}). Waiting for port 5001 to free...", timeout=4)
        # Poll until port is free + container gone (max 60s)
        for _ in range(20):
            code, out, _ = lr.ssh_exec(
                host, user, pw,
                "ss -lnt 'sport = :5001' | tail -n +2 | wc -l",
                timeout=8,
            )
            try: free = int((out or "1").strip()) == 0
            except Exception: free = False
            if free: break
            time.sleep(3.0)
        self.app.call_from_thread(self.app.refresh_linux_running)
        ok, msg = lr.start_config(host, user, pw, self.cfg)
        sev = "information" if ok else "error"
        self.app.call_from_thread(
            self.app.notify, f"Load: {msg}", severity=sev, timeout=8)
        self.app.call_from_thread(self.app.refresh_linux_running)

    def _do_unload(self) -> None:
        cfg = self.cfg
        msg = f"Stop vLLM on popos?\nSIGTERM launch-*.sh → docker compose down + power reset."
        def _yes(ok: bool):
            if not ok: return
            self.app.notify("Stopping vLLM on popos...", timeout=4)
            self.app.run_worker(
                lambda: self._unload_blocking(),
                thread=True, exclusive=True,
            )
        self.app.push_screen(ConfirmModal(msg), _yes)

    def _unload_blocking(self) -> None:
        from .. import linux_runtime as lr
        host, user, pw = self._ssh()
        ok, msg = lr.stop_running(host, user, pw, self.bundle.linux_shared_defaults)
        sev = "information" if ok else "error"
        self.app.call_from_thread(self.app.notify, f"Unload: {msg}", severity=sev, timeout=8)
        self.app.call_from_thread(self.app.refresh_linux_running)

    def _do_test(self) -> None:
        cfg = self.cfg
        sd = self.bundle.linux_shared_defaults
        host = sd["ssh_host"]
        served = sd.get("served_model_name", "qwen3.6-27b-turbo")
        self.app.notify("Testing inference on popos...", timeout=2)
        self.app.run_worker(
            lambda: self._test_blocking(host, cfg.port, served),
            thread=True, exclusive=True,
        )

    def _test_blocking(self, host: str, port: int, served: str) -> None:
        from .. import inference
        result = inference.test_chat(port, model=served, host=host)
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

    def _do_log(self) -> None:
        self.app.run_worker(
            lambda: self._log_blocking(), thread=True, exclusive=True,
        )

    def _log_blocking(self) -> None:
        from .. import linux_runtime as lr
        host, user, pw = self._ssh()
        tail = lr.fetch_log_tail(host, user, pw, self.cfg.id, lines=80)
        body = f"[#8b949e]/tmp/vllm-launcher-{self.cfg.id}.log[/]\n\n{tail or '(empty)'}"
        self.app.call_from_thread(
            self.app.push_screen, ResultModal(f"Log → {self.cfg.id}", body)
        )

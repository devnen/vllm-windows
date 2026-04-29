from __future__ import annotations
import os
import sys
from textual.app import App
from textual.binding import Binding
from textual.worker import get_current_worker

from . import config as cfgmod
from . import runtime
from .screens.dashboard import Dashboard
from .screens.detail import DetailScreen
from .screens.help import HelpScreen

# Linux/remote-host integration is disabled by default in the public release.
# Set VLLM_WINDOWS_ENABLE_LINUX=1 to surface the Linux tab; remote-host work
# will be revisited in a follow-up release.
_ENABLE_LINUX = os.environ.get("VLLM_WINDOWS_ENABLE_LINUX", "").lower() in ("1", "true", "yes", "on")
if _ENABLE_LINUX:
    from . import linux_runtime
    from .screens.linux_detail import LinuxDetailScreen


class LauncherApp(App):
    TITLE = "vLLM Launcher"
    SUB_TITLE = "Qwen3.6-27B AutoRound · 2× RTX 3090"

    BINDINGS = [
        Binding("ctrl+w", "launch_web", "Web UI", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("h", "help", "Help", show=False),
    ]

    CSS = """
    Screen { background: #0d1117; color: #e6edf3; }
    Header { background: #11161d; color: #58a6ff; }
    Footer { background: #11161d; color: #8b949e; }
    """

    def __init__(self):
        super().__init__()
        self.bundle = cfgmod.load()
        self.running: dict = {}
        self.running_ids: set[str] = set()
        self.linux_running: dict = {}
        self.linux_running_ids: set[str] = set()
        self._dashboard: Dashboard | None = None

    def on_mount(self) -> None:
        self._dashboard = Dashboard(self.bundle)
        self.install_screen(self._dashboard, name="dashboard")
        self.install_screen(HelpScreen(self.bundle), name="help")
        self.push_screen("dashboard")
        self.set_interval(2.0, self.refresh_running)
        self.refresh_running()
        if _ENABLE_LINUX:
            self.set_interval(5.0, self._maybe_refresh_linux)
            self.refresh_linux_running()
            self.refresh_linux_alive()

    def open_detail(self, cfg_id: str) -> None:
        cfg = next((c for c in self.bundle.windows if c.id == cfg_id), None)
        if cfg is None:
            return
        self.push_screen(DetailScreen(cfg, self.bundle))

    def open_linux_detail(self, cfg_id: str) -> None:
        cfg = next((c for c in self.bundle.linux if c.id == cfg_id), None)
        if cfg is None:
            return
        self.push_screen(LinuxDetailScreen(cfg, self.bundle))

    def refresh_running(self) -> None:
        self.run_worker(self._poll_running, thread=True, exclusive=True)

    def _poll_running(self) -> None:
        ports = sorted({c.port for c in self.bundle.windows})
        running = runtime.detect_running(ports, self.bundle.windows)
        ids = set(running.keys())
        self.call_from_thread(self._apply_running, running, ids)

    def _apply_running(self, running, ids):
        self.running = running
        self.running_ids = ids
        if self._dashboard is not None:
            self._dashboard.update_running(ids)

    def _maybe_refresh_linux(self) -> None:
        # Cheap throttle: only poll when the Linux tab is active OR a Linux detail is open
        active = self._dashboard is not None and self._dashboard._active_tab == "linux"
        from .screens.linux_detail import LinuxDetailScreen
        in_detail = isinstance(self.screen, LinuxDetailScreen)
        if active or in_detail:
            self.refresh_linux_running()
            self.refresh_linux_alive()

    def refresh_linux_alive(self) -> None:
        self.run_worker(self._poll_linux_alive, thread=True, exclusive=False)

    def _poll_linux_alive(self) -> None:
        sd = self.bundle.linux_shared_defaults
        alive = linux_runtime.ping_alive(sd.get("ssh_host", "127.0.0.1"), timeout_s=2)
        self.call_from_thread(self._apply_linux_alive, alive)

    def _apply_linux_alive(self, alive: bool) -> None:
        if self._dashboard is not None:
            self._dashboard.update_host_pill(alive)

    def refresh_linux_running(self) -> None:
        self.run_worker(self._poll_linux, thread=True, exclusive=False)

    def _poll_linux(self) -> None:
        sd = self.bundle.linux_shared_defaults
        try:
            running = linux_runtime.detect_running(
                sd["ssh_host"], sd["ssh_user"], sd["ssh_password"],
                sd, self.bundle.linux,
            )
        except Exception:
            running = {}
        ids = set(running.keys())
        self.call_from_thread(self._apply_linux_running, running, ids)

    def _apply_linux_running(self, running, ids):
        self.linux_running = running
        self.linux_running_ids = ids
        if self._dashboard is not None:
            self._dashboard.update_linux_running(ids)

    def switch_to_tab(self, tab: str) -> None:
        if self._dashboard is not None:
            self._dashboard.switch_to_tab(tab)

    def do_linux_shutdown(self) -> None:
        from .screens.detail import ConfirmModal, ResultModal
        sd = self.bundle.linux_shared_defaults
        host = sd.get("ssh_host", "?")
        running = sorted(self.linux_running_ids)
        running_line = f"\n[b #d29922]Currently running:[/] {', '.join(running)}\nIt will be unloaded first.\n" if running else ""
        msg = (
            f"[b #f85149]Shut down {host}?[/]\n"
            f"{running_line}\n"
            f"Steps:\n"
            f"  1. Stop any running vLLM (graceful unload)\n"
            f"  2. Enable Wake-on-LAN (magic) on {sd.get('nic_name','enp34s0')}\n"
            f"  3. sudo /sbin/shutdown now\n"
            f"  4. Wait until ping stops responding\n\n"
            f"After this, only the Wake button can bring it back."
        )
        def _yes(ok: bool):
            if not ok: return
            self.notify(f"Shutting down {host}...", timeout=4)
            self.run_worker(self._shutdown_blocking, thread=True, exclusive=True)
        self.push_screen(ConfirmModal(msg), _yes)

    def _shutdown_blocking(self) -> None:
        from .screens.detail import ResultModal
        sd = self.bundle.linux_shared_defaults
        progress: list[str] = []
        def _p(s: str):
            progress.append(s)
            self.call_from_thread(self.notify, s, timeout=3)
        ok, msg = linux_runtime.shutdown_box(
            sd["ssh_host"], sd["ssh_user"], sd["ssh_password"], sd, progress=_p,
        )
        body = "\n".join(f"  • {p}" for p in progress) + f"\n\n[b]{'OK' if ok else 'FAIL'}:[/] {msg}"
        col = "#3fb950" if ok else "#f85149"
        self.call_from_thread(
            self.push_screen, ResultModal(f"Shutdown → {sd['ssh_host']}",
                                          f"[b {col}]{msg}[/]\n\n{body}"))
        self.call_from_thread(self.refresh_linux_running)
        self.call_from_thread(self.refresh_linux_alive)

    def do_linux_wake(self) -> None:
        from .screens.detail import ConfirmModal, ResultModal
        sd = self.bundle.linux_shared_defaults
        msg = (
            f"Send Wake-on-LAN magic packet?\n"
            f"  MAC:       {sd.get('ssh_mac','?')}\n"
            f"  Broadcast: {sd.get('broadcast_ip','255.255.255.255')}:9 + :7\n\n"
            f"After sending, the launcher will ping {sd.get('ssh_host','?')} for up to 3 minutes."
        )
        def _yes(ok: bool):
            if not ok: return
            self.notify("Sending WOL packet...", timeout=3)
            self.run_worker(self._wake_blocking, thread=True, exclusive=True)
        self.push_screen(ConfirmModal(msg), _yes)

    def _wake_blocking(self) -> None:
        from .screens.detail import ResultModal
        sd = self.bundle.linux_shared_defaults
        # Aggressive WOL: send to broadcast + limited broadcast + unicast,
        # ports 9 + 7, repeated several rounds. Some setups drop one variant.
        import socket, time
        mac_clean = sd["ssh_mac"].replace(":", "").replace("-", "").lower()
        payload = bytes.fromhex("ff" * 6 + mac_clean * 16)
        targets = [
            (sd.get("broadcast_ip", "255.255.255.255"), 9),
            (sd.get("broadcast_ip", "255.255.255.255"), 7),
            ("255.255.255.255", 9),
            (sd["ssh_host"], 9),
            (sd["ssh_host"], 7),
        ]
        sent = 0
        last_err = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for _round in range(3):
                for tgt in targets:
                    try: s.sendto(payload, tgt); sent += 1
                    except Exception as e: last_err = str(e)
                time.sleep(1.0)
            s.close()
        except Exception as e:
            last_err = str(e)
        if sent == 0:
            self.call_from_thread(
                self.push_screen,
                ResultModal("Wake failed", f"[#f85149]could not send WOL: {last_err}[/]"))
            return
        msg = f"sent {sent} magic packet(s) across 5 targets × 3 rounds"
        self.call_from_thread(
            self.notify, f"WOL sent ({sent} packets). Pinging {sd['ssh_host']}...", timeout=3)
        alive = linux_runtime.wait_until_online(sd["ssh_host"], max_seconds=180)

        ssh_ok = False
        if alive:
            # ssh may take another 10–20s after ping comes back
            for _ in range(15):
                code, _o, _e = linux_runtime.ssh_exec(
                    sd["ssh_host"], sd["ssh_user"], sd["ssh_password"],
                    "echo READY", timeout=5,
                )
                if code == 0:
                    ssh_ok = True; break
                time.sleep(2.0)

        if alive:
            body = (
                f"[b #3fb950]● ONLINE[/]\n\n"
                f"  • {msg}\n"
                f"  • ping {sd['ssh_host']} → reachable\n"
                f"  • ssh ready → {'yes' if ssh_ok else 'not yet (still booting)'}\n\n"
                f"vLLM is NOT running — open the Linux tab and click any active "
                f"config card → Load to start one (recommended: [b #58a6ff]v17[/])."
            )
        else:
            body = (
                f"[b #f85149]✖ still offline after 3 min[/]\n\n"
                f"  • {msg}\n"
                f"  • ping {sd['ssh_host']} → no response\n\n"
                f"[b #d29922]Most likely cause: BIOS / motherboard.[/]\n"
                f"  Magic packets are being sent correctly. If the box doesn't\n"
                f"  wake, the motherboard isn't keeping the NIC powered at S5.\n\n"
                f"  Check BIOS:\n"
                f"    • Power Management → Wake on LAN / 'Power On by PCI-E' = [b]Enabled[/]\n"
                f"    • ErP / EuP / Deep Sleep = [b]Disabled[/] (ErP cuts NIC power)\n"
                f"    • Some boards: also enable 'Resume by PCI Device'\n\n"
                f"  Linux side (already handled by Shutdown flow):\n"
                f"    • [#8b949e]sudo ethtool -s enp34s0 wol g[/] is set before shutdown\n\n"
                f"Press the physical power button to recover."
            )
        self.call_from_thread(
            self.push_screen, ResultModal(f"Wake → {sd['ssh_host']}", body))
        self.call_from_thread(self.refresh_linux_alive)
        self.call_from_thread(self.refresh_linux_running)

    def action_help(self) -> None:
        self.push_screen("help")

    def action_launch_web(self) -> None:
        from .serve import start_web_server
        command = f'"{sys.executable}" -m vllm_launcher'
        try:
            url = start_web_server(command=command, title=self.TITLE, port=8765)
        except ImportError:
            self.notify("textual-serve not installed", severity="error", timeout=5); return
        except Exception as e:
            self.notify(f"Web UI failed: {e}", severity="error", timeout=5); return
        self.notify(f"Web UI at {url}")

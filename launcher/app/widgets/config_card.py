from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from rich.text import Text

from ..config import WinConfig, LinuxConfig

STATUS_DOT = {
    "running":     ("●", "#3fb950"),
    "stopped":     ("○", "#8b949e"),
    "blocked":     ("✖", "#f85149"),
    "superseded":  ("◌", "#d29922"),
    "conditional": ("◐", "#d29922"),
}


def _status_key(cfg: WinConfig, is_running: bool) -> str:
    if is_running:
        return "running"
    if cfg.status == "blocked":
        return "blocked"
    if cfg.status == "superseded":
        return "superseded"
    if cfg.status == "conditional":
        return "conditional"
    return "stopped"


class ConfigCard(Static):
    DEFAULT_CSS = """
    ConfigCard {
        background: #161b22;
        border: solid #30363d;
        padding: 0 1;
        height: 11;
        width: 1fr;
        margin: 0 1 1 0;
    }
    ConfigCard:focus {
        border: solid #58a6ff;
        background: #1a2230;
    }
    ConfigCard.-running { border-left: thick #3fb950; }
    ConfigCard.-blocked { border-left: thick #f85149; }
    ConfigCard.-legacy  { border-left: thick #d29922; }
    """

    can_focus = True

    def __init__(self, cfg: "WinConfig | LinuxConfig", is_running: bool = False, **kw):
        super().__init__(**kw)
        self.cfg = cfg
        self.running = is_running
        self._refresh_classes()

    def _refresh_classes(self) -> None:
        self.remove_class("-running", "-blocked", "-legacy")
        if self.running:
            self.add_class("-running")
        elif self.cfg.status == "blocked":
            self.add_class("-blocked")
        elif self.cfg.tier == "legacy":
            self.add_class("-legacy")

    def render(self):
        cfg = self.cfg
        sk = _status_key(cfg, self.running)
        dot, color = STATUS_DOT[sk]
        label = "RUNNING" if self.running else sk.upper()

        t = Text()
        t.append(f"{cfg.id:<14}", style="bold #e6edf3")
        t.append(" " * max(1, 28 - len(cfg.id)))
        t.append(f"{dot} {label}", style=f"bold {color}")
        t.append("\n")
        t.append(cfg.tagline, style="italic #8b949e")
        t.append("\n\n")

        def chip(k: str, v: str, style="#58a6ff"):
            t.append(f"{k}", style="dim #8b949e"); t.append(f" {v}  ", style=style)

        spec = "—"
        if cfg.mtp_n is not None:
            spec = f"MTP{cfg.mtp_n}"
        elif cfg.draft_model_n is not None:
            spec = f"draft{cfg.draft_model_n}"
        chip("GPU", cfg.gpu)
        chip("TP", str(cfg.tp))
        chip("PP", str(cfg.pp))
        chip("spec", spec)
        t.append("\n")
        chip("ctx", f"{cfg.ctx//1000}k")
        chip("port", str(cfg.port))
        dec = cfg.decode_tps
        if dec is None and cfg.decode_tps_short is not None:
            dec = cfg.decode_tps_short
        chip("decode", f"{dec:.1f} t/s" if dec else "n/a",
             style="#3fb950" if dec else "#8b949e")
        t.append("\n")
        if isinstance(cfg, LinuxConfig):
            vis = "vision-on" if cfg.vision_on else "novision"
            vcol = "#58a6ff" if cfg.vision_on else "#8b949e"
            t.append(f"  {vis}  ", style=f"dim {vcol}")
            if cfg.kv_dtype:
                t.append(f"  KV {cfg.kv_dtype}", style="dim #8b949e")
        else:
            if cfg.power_cap_w:
                t.append(f"  {cfg.power_cap_w}W  ", style="dim #d29922")
            t.append(f"  tier: {cfg.tier}", style="dim #8b949e")
        return t

    def update_running(self, is_running: bool) -> None:
        if is_running != self.running:
            self.running = is_running
            self._refresh_classes()
            self.refresh()

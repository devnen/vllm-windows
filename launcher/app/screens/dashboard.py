from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Grid, Horizontal
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, ContentSwitcher, Button

from ..widgets.config_card import ConfigCard
from ..widgets.nav_bar import NavBar
from ..config import WinConfig, LinuxConfig


class Dashboard(Screen):
    DEFAULT_CSS = """
    Dashboard { background: #0d1117; color: #e6edf3; }
    .cards-grid {
        grid-size: 3;
        grid-gutter: 1 1;
        padding: 1 2 1 2;
        height: auto;
    }
    .legacy-section-title {
        padding: 1 2;
        color: #d29922;
        text-style: bold;
    }
    .linux-host-line {
        padding: 1 3 0 3;
        color: #8b949e;
        height: auto;
    }
    #linux-power-bar {
        height: 4;
        padding: 0 2;
        margin: 1 2 0 2;
        background: #11161d;
        border-top: solid #30363d;
        border-bottom: solid #30363d;
    }
    #linux-power-bar Static.host-pill {
        padding: 1 2;
        margin: 0 2 0 0;
        height: 3;
        content-align: left middle;
        width: 32;
    }
    #linux-power-bar Static.host-pill-up {
        background: #11202f;
        color: #3fb950;
        text-style: bold;
    }
    #linux-power-bar Static.host-pill-down {
        background: #2d0a0f;
        color: #f85149;
        text-style: bold;
    }
    #linux-power-bar Static.host-pill-unknown {
        background: #1c1c1c;
        color: #8b949e;
    }
    #linux-power-bar Button {
        margin: 0 1 0 0;
        min-width: 16;
        height: 3;
        content-align: center middle;
    }
    #linux-power-bar Button#btn-shutdown { background: #2d0a0f; color: #f85149; }
    #linux-power-bar Button#btn-wake     { background: #11202f; color: #58a6ff; }
    #linux-power-bar Button#btn-refresh  { background: #21262d; }
    """

    BINDINGS = [
        ("h", "help", "Help"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, bundle, *a, **kw):
        super().__init__(*a, **kw)
        self.bundle = bundle
        self.cards: dict[str, ConfigCard] = {}
        self.linux_cards: dict[str, ConfigCard] = {}
        self._active_tab = "windows"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield NavBar(active=self._active_tab)
        with ContentSwitcher(initial="pane-windows", id="tab-content"):
            with VerticalScroll(id="pane-windows"):
                active = [c for c in self.bundle.windows if c.tier == "active"]
                legacy = [c for c in self.bundle.windows if c.tier == "legacy"]
                blocked = [c for c in self.bundle.windows if c.tier == "blocked"]

                yield Static("[b #58a6ff]Active configs[/]", classes="legacy-section-title")
                with Grid(classes="cards-grid") as g:
                    g.styles.grid_size_rows = max(1, (len(active) + 2) // 3)
                    for c in active:
                        card = ConfigCard(c, is_running=False, id=f"card-{c.id}")
                        self.cards[c.id] = card
                        yield card

                if legacy:
                    yield Static("[b #d29922]Legacy[/]", classes="legacy-section-title")
                    with Grid(classes="cards-grid") as g:
                        g.styles.grid_size_rows = max(1, (len(legacy) + 2) // 3)
                        for c in legacy:
                            card = ConfigCard(c, is_running=False, id=f"card-{c.id}")
                            self.cards[c.id] = card
                            yield card

                if blocked:
                    yield Static("[b #f85149]Blocked[/]", classes="legacy-section-title")
                    with Grid(classes="cards-grid") as g:
                        for c in blocked:
                            card = ConfigCard(c, is_running=False, id=f"card-{c.id}")
                            self.cards[c.id] = card
                            yield card
            with VerticalScroll(id="pane-linux"):
                sd = self.bundle.linux_shared_defaults
                host_line = (
                    f"[#8b949e]ssh[/] [#d29922]{sd.get('ssh_user','?')}@{sd.get('ssh_host','?')}[/]"
                    f"  [#8b949e]mac[/] [#e6edf3]{sd.get('ssh_mac','?')}[/]"
                    f"  [#8b949e]proj[/] [#e6edf3]{sd.get('project_dir','?')}[/]"
                )
                yield Static(host_line, classes="linux-host-line")

                with Horizontal(id="linux-power-bar"):
                    yield Static("? UNKNOWN", id="host-pill",
                                 classes="host-pill host-pill-unknown")
                    yield Button("Shutdown", id="btn-shutdown", variant="error")
                    yield Button("Wake (WOL)", id="btn-wake", variant="primary")
                    yield Button("Refresh", id="btn-refresh")

                active_l = [c for c in self.bundle.linux if c.tier == "active"]
                legacy_l = [c for c in self.bundle.linux if c.tier == "legacy"]
                blocked_l = [c for c in self.bundle.linux if c.tier == "blocked"]

                yield Static("[b #d29922]Active configs[/]", classes="legacy-section-title")
                with Grid(classes="cards-grid") as g:
                    g.styles.grid_size_rows = max(1, (len(active_l) + 2) // 3)
                    for c in active_l:
                        card = ConfigCard(c, is_running=False, id=f"lcard-{c.id}")
                        self.linux_cards[c.id] = card
                        yield card

                if legacy_l:
                    yield Static("[b #d29922]Legacy[/]", classes="legacy-section-title")
                    with Grid(classes="cards-grid") as g:
                        g.styles.grid_size_rows = max(1, (len(legacy_l) + 2) // 3)
                        for c in legacy_l:
                            card = ConfigCard(c, is_running=False, id=f"lcard-{c.id}")
                            self.linux_cards[c.id] = card
                            yield card

                if blocked_l:
                    yield Static("[b #f85149]Blocked[/]", classes="legacy-section-title")
                    with Grid(classes="cards-grid") as g:
                        g.styles.grid_size_rows = max(1, (len(blocked_l) + 2) // 3)
                        for c in blocked_l:
                            card = ConfigCard(c, is_running=False, id=f"lcard-{c.id}")
                            self.linux_cards[c.id] = card
                            yield card
        yield Footer()

    def switch_to_tab(self, tab: str) -> None:
        if tab not in ("windows", "linux") or tab == self._active_tab:
            return
        self._active_tab = tab
        self.query_one("#tab-content", ContentSwitcher).current = f"pane-{tab}"
        self.query_one(NavBar).set_active(tab)
        if tab == "linux":
            self.app.refresh_linux_running()
            self.app.refresh_linux_alive()

    def update_running(self, running_ids: set[str]) -> None:
        for cid, card in self.cards.items():
            card.update_running(cid in running_ids)

    def update_linux_running(self, running_ids: set[str]) -> None:
        for cid, card in self.linux_cards.items():
            card.update_running(cid in running_ids)

    def update_host_pill(self, alive: bool | None) -> None:
        try:
            pill = self.query_one("#host-pill", Static)
        except Exception:
            return
        sd = self.bundle.linux_shared_defaults
        host = sd.get("ssh_host", "?")
        if alive is True:
            pill.update(f"● {host} ONLINE")
            pill.set_classes("host-pill host-pill-up")
        elif alive is False:
            pill.update(f"○ {host} OFFLINE")
            pill.set_classes("host-pill host-pill-down")
        else:
            pill.update(f"? {host} CHECKING")
            pill.set_classes("host-pill host-pill-unknown")

    def action_help(self) -> None:
        self.app.push_screen("help")

    def action_refresh(self) -> None:
        self.app.refresh_running()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid == "btn-shutdown":
            ev.stop(); self.app.do_linux_shutdown()
        elif bid == "btn-wake":
            ev.stop(); self.app.do_linux_wake()
        elif bid == "btn-refresh":
            ev.stop(); self.app.refresh_linux_running()

    def on_click(self, ev) -> None:
        w = ev.widget
        if isinstance(w, Button):  # let on_button_pressed handle it
            return
        while w is not None:
            if isinstance(w, ConfigCard):
                self._open(w.cfg)
                return
            w = getattr(w, "parent", None)

    def on_key(self, ev) -> None:
        if ev.key == "enter":
            f = self.focused
            if isinstance(f, ConfigCard):
                self._open(f.cfg)
                ev.stop()

    def _open(self, cfg) -> None:
        if isinstance(cfg, LinuxConfig):
            self.app.open_linux_detail(cfg.id)
        else:
            self.app.open_detail(cfg.id)

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Footer, Static


SYM = {
    "ok":      ("[b #3fb950]✔[/]", "#3fb950"),
    "warn":    ("[b #d29922]⚠[/]", "#d29922"),
    "bad":     ("[b #f85149]✖[/]", "#f85149"),
    "blocked": ("[b #f85149]⊘[/]", "#f85149"),
}


class HelpScreen(Screen):
    DEFAULT_CSS = """
    HelpScreen { background: #0d1117; color: #e6edf3; }
    #wrap {
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
        margin: 1 2;
        height: 1fr;
    }
    """

    BINDINGS = [("escape", "back", "Back"), ("h", "back", "Back")]

    def __init__(self, bundle, **kw):
        super().__init__(**kw)
        self.bundle = bundle

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="wrap"):
            yield Static(self._build_text())
        yield Footer()

    def _build_text(self) -> str:
        lines: list[str] = []
        lines.append("[b #58a6ff]Spec-decode × parallelism compatibility matrix[/]\n")
        for r in self.bundle.compatibility_matrix:
            sym, _ = SYM.get(r["status"], ("?", "#8b949e"))
            lines.append(f"  {sym}  [b]{r['combo']:<30}[/]  [#8b949e]{r['note']}[/]")

        lines.append("\n[b #58a6ff]Key bindings[/]\n")
        for k, v in [
            ("Tab / Shift+Tab", "Cycle cards"),
            ("Enter",          "Open detail"),
            ("Esc",            "Back / quit"),
            ("h",              "This help screen"),
            ("r",              "Refresh running status"),
            ("Ctrl+W",         "Web UI"),
            ("L / U / T",      "Load / Unload / Test (in detail screen)"),
        ]:
            lines.append(f"  [#8b949e]{k:<18}[/]  {v}")
        return "\n".join(lines)

    def action_back(self) -> None:
        self.app.pop_screen()

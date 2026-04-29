"""Top tabbed navigation bar.

Layout:

    [Windows] [Linux]

Tabs are Buttons. The active tab is marked with the ``tab-active`` class;
each tab also gets a per-tab color class (``tab-windows``, ``tab-linux``)
for individual tinting.

Textual's default Button has a 3D push effect: a top "highlight" border
(`border-top: tall $surface-lighten-1`) that swaps on `:hover` and
`.-active`, plus a `:focus` `background-tint` + bold. That makes the
label visually shift up on hover, and stick "pressed" once a click moves
focus to the button. We neutralise it here by:
  * forcing fixed `border` (no top highlight) in every state,
  * overriding `:focus` so it doesn't change appearance,
  * overriding `.-active` so a press doesn't swap borders.
The bar dispatches clicks to ``App.switch_to_tab(name)``.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button


TABS: tuple[tuple[str, str], ...] = (
    ("windows", "Windows"),
    ("linux", "Linux"),
)


class NavBar(Horizontal):
    """Top-of-screen tab bar. Construct with ``NavBar(active="windows")``."""

    DEFAULT_CSS = """
    NavBar {
        height: 3;
        width: 100%;
        padding: 0;
        background: #0d1117;
    }
    NavBar Button {
        margin: 0;
        height: 3;
        min-width: 12;
        padding: 0 2;
        border: none !important;
        border-top: tall #0d1117 !important;
        border-bottom: heavy #0d1117 !important;
        background: #0d1117 !important;
        color: #8b949e;
        text-style: none;
        content-align: center middle;
    }
    NavBar Button.tab-windows { color: #58a6ff; }
    NavBar Button.tab-linux   { color: #d29922; }

    /* Kill Button's :focus styling — clicks shouldn't change the look */
    NavBar Button:focus {
        text-style: none;
        background-tint: transparent;
    }
    /* Kill Button's pressed-state border swap that shifts the label down */
    NavBar Button.-active {
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #0d1117;
        background: #0d1117;
        tint: transparent;
    }

    NavBar Button:hover {
        color: #ffffff;
        text-style: bold;
        border: none;
    }
    NavBar Button.tab-windows:hover {
        background: #10284a !important;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #58a6ff !important;
    }
    NavBar Button.tab-linux:hover {
        background: #3e2d0a !important;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #d29922 !important;
    }

    NavBar Button.tab-windows.tab-active {
        color: #ffffff;
        text-style: bold;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #58a6ff !important;
    }
    NavBar Button.tab-linux.tab-active {
        color: #ffffff;
        text-style: bold;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #d29922 !important;
    }
    NavBar Button.tab-windows.tab-active:hover {
        background: #10284a !important;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #58a6ff !important;
    }
    NavBar Button.tab-linux.tab-active:hover {
        background: #3e2d0a !important;
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #d29922 !important;
    }
    /* Active-tab .-active (clicking the already-selected tab) — keep it stable */
    NavBar Button.tab-windows.tab-active.-active {
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #58a6ff !important;
        background: #0d1117;
        tint: transparent;
    }
    NavBar Button.tab-linux.tab-active.-active {
        border: none;
        border-top: tall #0d1117;
        border-bottom: heavy #d29922 !important;
        background: #0d1117;
        tint: transparent;
    }
    """

    def __init__(self, *, active: str = "windows", id: str | None = "nav-bar") -> None:
        super().__init__(id=id)
        self._active = active

    def compose(self) -> ComposeResult:
        for tab_id, label in TABS:
            classes = f"tab-{tab_id}"
            if tab_id == self._active:
                classes += " tab-active"
            yield Button(label, id=f"nav-{tab_id}", classes=classes)

    def set_active(self, tab: str) -> None:
        self._active = tab
        for tab_id, _ in TABS:
            try:
                btn = self.query_one(f"#nav-{tab_id}", Button)
            except Exception:
                continue
            cls = f"tab-{tab_id}"
            if tab_id == tab:
                cls += " tab-active"
            btn.set_classes(cls)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("nav-"):
            return
        tab = bid[len("nav-") :]
        event.stop()
        if tab == self._active:
            return
        switcher = getattr(self.app, "switch_to_tab", None)
        if callable(switcher):
            switcher(tab)

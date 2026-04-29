from __future__ import annotations
import threading
import time
import webbrowser

_server_thread: threading.Thread | None = None


def start_web_server(command: str, host: str = "localhost", port: int = 8765,
                    title: str = "vLLM Launcher", open_browser: bool = True) -> str:
    global _server_thread
    url = f"http://{host}:{port}"
    if _server_thread is not None and _server_thread.is_alive():
        if open_browser:
            webbrowser.open(url)
        return url
    from textual_serve.server import Server
    server = Server(command=command, host=host, port=port, title=title)
    _server_thread = threading.Thread(target=server.serve, daemon=True)
    _server_thread.start()
    if open_browser:
        time.sleep(1.0)
        webbrowser.open(url)
    return url

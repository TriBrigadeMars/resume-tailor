"""ResumeTailor Desktop — pure Python native desktop app.

Uses pywebview (native Edge WebView2 window) + pystray (system tray).
No Electron, no Node — fully Python.

Run:  .venv\\Scripts\\python desktop.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from io import BytesIO

import webview
import pystray
from PIL import Image, ImageDraw
from urllib.request import urlopen
from urllib.error import URLError

# Import the Flask app (will be spawned inside this process)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app  # noqa: E402


def _find_free_port(start: int = 8000, tries: int = 10) -> int:
    import socket

    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range.")


def _load_tray_icon() -> Image.Image:
    """Load the ICO and return a PIL Image for the tray."""
    ico_path = os.path.join(os.path.dirname(__file__), "ResumeTailor.ico")
    if os.path.exists(ico_path):
        img = Image.open(ico_path)
    else:
        # Fallback: a simple blue square with a sparkle
        img = Image.new("RGBA", (32, 32), (56, 130, 246, 255))
        d = ImageDraw.Draw(img)
        d.polygon(
            [(16, 2), (18, 8), (24, 10), (18, 12), (16, 18), (14, 12), (8, 10), (14, 8)],
            fill=(253, 224, 71, 255),
        )
    return img.resize((32, 32), Image.LANCZOS)


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(f"{url}/", timeout=1)
            return
        except (URLError, OSError):
            time.sleep(0.3)
    raise RuntimeError("Backend did not start in time.")


class Api:
    """Python API exposed to the webview JS via window.pywebview.api.

    Lets the desktop UI save generated documents using a native save dialog,
    which is far more reliable than blob-URL downloads inside WebView2.
    """

    def save_document(self, content: str, doc_type: str, fmt: str) -> dict:
        import io
        import tkinter as tk
        from tkinter import filedialog

        try:
            if fmt == "docx":
                import docgen
                document = docgen.markdown_to_docx(content)
                buffer = io.BytesIO()
                document.save(buffer)
                data = buffer.getvalue()
                default_ext = ".docx"
                filetypes = [("Word Document", "*.docx")]
            else:
                import docgen
                data = docgen.markdown_to_text(content).encode("utf-8")
                default_ext = ".txt"
                filetypes = [("Text File", "*.txt")]
        except Exception as exc:  # noqa: BLE001
            return {"saved": False, "message": f"Could not build document: {exc}"}

        base = "tailored_resume" if doc_type == "resume" else "cover_letter"

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=default_ext,
                filetypes=filetypes,
                initialfile=f"{base}{default_ext}",
                title="Save ResumeTailor document",
            )
        finally:
            root.destroy()

        if not filename:
            return {"saved": False, "message": "Save cancelled."}

        try:
            with open(filename, "wb") as f:
                f.write(data)
        except Exception as exc:  # noqa: BLE001
            return {"saved": False, "message": f"Could not write file: {exc}"}
        return {"saved": True, "path": filename}


class ResumeTailorDesktop:
    def __init__(self):
        self.port: int = 0
        self.url: str = ""
        self.window = None
        self.tray: pystray.Icon | None = None
        self._flask_thread: threading.Thread | None = None
        self._quitting = False

    def run(self) -> None:
        """Main entry point: start backend → tray → webview window."""
        self.port = _find_free_port()
        self.url = f"http://localhost:{self.port}"

        # Start Flask in a background daemon thread
        self._flask_thread = threading.Thread(
            target=self._start_flask, daemon=True
        )
        self._flask_thread.start()

        # Wait for Flask to be ready
        _wait_for_server(self.url)

        # Start system tray icon in its own thread
        tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        tray_thread.start()

        # Create and show the native web-view window (blocks the main thread)
        self.window = webview.create_window(
            "ResumeTailor",
            self.url,
            width=1280,
            height=850,
            min_size=(900, 600),
            confirm_close=False,  # we handle close ourselves
            js_api=Api(),
        )
        # Hide to tray on close or minimize; let the tray handle quit.
        self.window.events.closing += self._on_closing
        self.window.events.minimized += self._on_minimized

        webview.start(gui="edgechromium")

    # ---- Flask backend ----

    def _start_flask(self) -> None:
        """Run the Flask app, overriding env so it doesn't open a browser.

        The desktop app binds to loopback and is a trusted local application, so
        it explicitly allows browser-supplied MCP server configuration.
        """
        os.environ["AUTO_OPEN_BROWSER"] = "0"
        os.environ["HOST"] = "127.0.0.1"
        os.environ["PORT"] = str(self.port)
        os.environ["ALLOW_CLIENT_MCP_SERVERS"] = "1"
        try:
            app.app.run(host="127.0.0.1", port=self.port, debug=False)
        except Exception as exc:  # noqa: BLE001
            print(f"Flask error: {exc}")

    # ---- System tray ----

    def _run_tray(self) -> None:
        icon = _load_tray_icon()
        self.tray = pystray.Icon(
            "resume-tailor",
            icon,
            "ResumeTailor",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Show ResumeTailor", self._show_window, default=True
                ),
                pystray.MenuItem(
                    "Open in Browser", lambda: webbrowser.open(self.url)
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit_app),
            ),
        )
        self.tray.run()

    def _show_window(self, _=None, __=None) -> None:
        """Restore the webview window from the tray."""
        for w in webview.windows:
            try:
                w.show()
            except Exception:
                pass

    def _on_minimized(self) -> None:
        """When the window is minimized, hide it completely (to tray)."""
        for w in webview.windows:
            try:
                w.hide()
            except Exception:
                pass

    def _on_closing(self) -> bool:
        """Intercept window close: hide to tray instead of quitting."""
        if not self._quitting:
            for w in webview.windows:
                try:
                    w.hide()
                except Exception:
                    pass
            return False  # prevent close
        return True  # allow close during quit

    def _quit_app(self, _=None, __=None) -> None:
        """Full shutdown: stop tray, kill flask, exit."""
        self._quitting = True
        if self.tray:
            self.tray.stop()
        # Close all webview windows
        for w in webview.windows:
            try:
                w.destroy()
            except Exception:
                pass
        # Give threads a moment then hard exit (Flask is daemon-threaded)
        time.sleep(0.3)
        os._exit(0)


if __name__ == "__main__":
    ResumeTailorDesktop().run()

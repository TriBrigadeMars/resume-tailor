"""Small shared networking helpers."""

from __future__ import annotations

import socket


def find_free_port(start: int = 8000, tries: int = 10) -> int:
    """Return the first TCP port in [start, start+tries) bindable on localhost."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range.")
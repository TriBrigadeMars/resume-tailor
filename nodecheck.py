"""Detect whether stdio MCP servers can run on this host.

MCP servers launched via stdio typically use ``npx`` (Node.js package runner),
which only exists when Node.js is installed and on ``PATH``. When the desktop
executable is run on a clean Windows machine without Node, calling ``npx``
would raise ``FileNotFoundError`` (or, on Windows, confuse users with a
separate console window popping up before the error). Detecting this up
front lets the app:

* skip stdio servers gracefully instead of crashing,
* warn the user that stdio MCP requires Node, while HTTP MCP still works.

This is intentionally a thin wrapper so it can be monkeypatched in tests
and called repeatedly without state.
"""

from __future__ import annotations

import shutil
import subprocess


def npx_available() -> bool:
    """Return True if ``npx`` is on PATH and responds to ``--version``.

    Tries both ``npx`` and ``npx.cmd`` (Windows uses the latter when ``PATHEXT``
    is configured the usual way; ``shutil.which`` only sees the un-suffixed
    name unless we ask explicitly).
    """
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return False
    try:
        result = subprocess.run(
            [npx, "--version"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        # Defensive: an empty returncode-0 run with no output is almost certainly
        # a wrapper that didn't actually run npx. Treat it as unavailable.
        return bool(result.stdout or result.stderr)
    except Exception:
        return False


def stdio_mcp_supported(
    servers: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """Split MCP server configs into (supported, skipped) lists.

    HTTP servers are always supported — they only need a URL the app can
    reach. stdio servers require ``npx`` (or any other command on PATH);
    when that is missing we drop them into the ``skipped`` bucket so the UI
    can warn the user by name instead of failing the whole MCP session.
    """
    supported: list[dict] = []
    skipped: list[dict] = []
    has_npx = npx_available()
    for server in servers or []:
        if server.get("type") == "stdio" and not has_npx:
            skipped.append(server)
        else:
            supported.append(server)
    return supported, skipped
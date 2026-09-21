"""Pytest configuration.

Stub the desktop-only modules (pywebview, pystray) so the test runner can
import ``desktop.py`` on machines where the desktop deps are not installed
(e.g. CI). The ``Api`` class itself is pure-Python and only needs the stub
to satisfy the module-level ``import webview`` / ``import pystray`` lines.
"""
import sys
import types


def _install_stub(name):
    mod = types.ModuleType(name)
    # ``webview.start`` is referenced in production code; give it a no-op.
    if name == "webview":
        mod.start = lambda *a, **kw: None
        mod.create_window = lambda *a, **kw: None
    sys.modules.setdefault(name, mod)


for _name in ("webview", "pystray", "pystray.Icon"):
    _install_stub(_name)

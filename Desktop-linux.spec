# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ResumeTailor Desktop on Linux.

Build a single-file executable:
    pyinstaller --clean --noconfirm Desktop-linux.spec

Notes:
- Linux distributions vary wildly; users are usually better served by
  ``pip install resumetailor`` than by running a frozen binary. We ship
  this spec mainly so CI can produce an AppImage-style artifact for
  testing and so contributors on Linux can preview the desktop GUI.
- GTK3 backend must be installed on the host (apt install
  python3-gi gir1.2-webkit2-4.0 on Debian/Ubuntu).
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("templates", "templates"), ("static", "static")]
binaries = []
hiddenimports = []

# ---- backend dependencies ----
for pkg in ("pymupdf", "docx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# mcp: collect manually to avoid the cli module (which calls sys.exit at import)
datas += collect_data_files("mcp")
hiddenimports += ["mcp", "mcp.types", "mcp.client.session", "mcp.client.stdio",
                   "mcp.client.streamable_http"]

# ---- desktop dependencies ----
for pkg in ("webview", "pystray", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("feedparser")

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "mcp.cli", "mcp.cli.cli"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ResumeTailor-Desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # smaller binary on Linux; syms available separately
    upx=True,
    upx_exclude=[],
    console=False,  # no terminal window in a GUI app
)

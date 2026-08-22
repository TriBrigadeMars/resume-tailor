# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ResumeTailor Desktop (pure Python + pywebview + pystray).

Build a single-file Windows .exe:
    .venv\Scripts\pyinstaller --clean --noconfirm Desktop.spec
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

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
from PyInstaller.utils.hooks import get_package_paths
mcp_base = get_package_paths("mcp")[1]
datas += collect_data_files("mcp")
hiddenimports += ["mcp", "mcp.types", "mcp.client.session", "mcp.client.stdio",
                   "mcp.client.streamable_http"]

# ---- desktop dependencies ----
for pkg in ("webview", "pystray", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# feedparser is pure Python but collect its data files
datas += collect_data_files("feedparser")

# ---- icon file ----
datas.append(("ResumeTailor.ico", "."))

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
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed — no console
    disable_windowed_traceback=False,
    icon="ResumeTailor.ico",
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

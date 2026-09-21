# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ResumeTailor Desktop on macOS.

Build a .app bundle:
    pyinstaller --clean --noconfirm Desktop-mac.spec

Notes:
- UPX is unreliable on macOS (and produces binaries that Gatekeeper is
  even more suspicious of). We deliberately leave it off here; the
  Windows specs keep UPX on.
- NSHighResolutionCapable=True makes the window crisp on Retina displays.
- icon.icns is the macOS icon bundle (use `iconutil` to generate from
  a .iconset). The build step is expected to provide it; if missing,
  PyInstaller falls back to a default.
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
    [],
    exclude_binaries=True,
    name="ResumeTailor-Desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX disabled on macOS — see top-of-file note
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ResumeTailor-Desktop",
)

app = BUNDLE(
    coll,
    name="ResumeTailor-Desktop.app",
    icon="icon.icns",
    bundle_identifier="com.tribrigademars.resumetailor",
    info_plist={
        "CFBundleDisplayName": "ResumeTailor",
        "CFBundleName": "ResumeTailor",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        # Required for the system-tray icon and the local loopback server.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)

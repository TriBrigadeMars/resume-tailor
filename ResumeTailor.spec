# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ResumeTailor.

Build a single-file Windows .exe:
    .venv\Scripts\pyinstaller --clean --noconfirm ResumeTailor.spec
"""

from PyInstaller.utils.hooks import collect_all

datas = [("templates", "templates"), ("static", "static")]
binaries = []
hiddenimports = []

# pymupdf ships native binaries; python-docx pulls in several helpers.
for pkg in ("pymupdf", "docx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
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
    name="ResumeTailor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app; browser auto-opens on launch
    disable_windowed_traceback=False,
    icon="ResumeTailor.ico",
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

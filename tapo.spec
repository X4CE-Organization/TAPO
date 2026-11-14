# -*- mode: python ; coding: utf-8 -*-
# Build a single-file TAPO executable with PyInstaller.
#   pyinstaller --clean --noconfirm tapo.spec

a = Analysis(
    ["tools/tapo_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[("std", "std")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="tapo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: портативный Math Idle.exe (один файл, без консоли)."""

import os

block_cipher = None

ROOT = os.path.abspath(os.getcwd())

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ("assets/fonts/Roboto-Regular.ttf", "assets/fonts"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # не нужны в игре и заметно раздувают .exe
        "numpy", "scipy", "pandas", "matplotlib", "PIL", "PyQt5", "PySide2",
        "tkinter", "test", "unittest", "pydoc", "setuptools", "pip",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.zipfiles,
    a.datas,
    [],
    name="MathIdle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # без консоли: обычный запуск. Отчёт --selftest пишется в mathidle-selftest.txt
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico" if os.path.exists("assets/icon.ico") else None,
)

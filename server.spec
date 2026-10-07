# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: сервер аккаунтов отдельной программой (MathIdleServer.exe).

Лежит рядом с игрой, чтобы игрок мог запустить сервер у себя, не ставя
Python. Console=True: игрок должен видеть, что сервер запустился и какой
адрес показывать в игре, — иначе «Registration doesn't work» снова.
"""

import os
import re

ROOT = os.path.dirname(os.path.abspath(SPEC))

# Версию берём из mathidle/config.py, чтобы она не разошлась с игрой.
with open(os.path.join(ROOT, "mathidle", "config.py"), encoding="utf-8") as fh:
    match = re.search(r'"version":\s*"([^"]+)"', fh.read())
VERSION = match.group(1) if match else "1.0.0"

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "server_main.py")],
    # server/ обязателен: account_server.py лежит там и импортирует
    # secret_store как обычный модуль, без указания пакета
    pathex=[ROOT, os.path.join(ROOT, "server")],
    binaries=[],
    datas=[],
    hiddenimports=["account_server", "secret_store"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy", "scipy", "pandas", "matplotlib", "PyQt5", "PySide2",
        "tkinter", "test", "unittest", "pydoc", "setuptools", "pip", "IPython",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MathIdleServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                    # игрок должен видеть адрес сервера
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MathIdleServer",
)
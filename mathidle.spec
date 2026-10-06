# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: портативный Math Idle (папка, onedir).

Почему onedir, а не onefile: onefile распаковывает DLL во временный каталог
во временный каталог в %TEMP% (имя начинается с подчёркивания и MEI), и
антивирус (в том числе Defender) периодически блокирует или удаляет
свежеизвлечённые файлы — сборка падает с «Failed to load Python DLL».
В onedir все DLL лежат рядом с .exe, распаковки нет, и запуск предсказуем.
Для пользователя это разница только в лишней папке, которую видно после
распаковки архива.
"""

import os

ROOT = os.path.dirname(os.path.abspath(SPEC))
block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "assets", "fonts", "Roboto-Regular.ttf"), "assets/fonts"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # не нужны в игре и заметно раздувают сборку
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
    name="MathIdle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MathIdle",
)

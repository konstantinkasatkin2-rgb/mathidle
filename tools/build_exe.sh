#!/usr/bin/env bash
# Собирает портативную Windows-версию в dist/MathIdle/ (PyInstaller, onedir)
# и упаковывает её в dist/MathIdle-windows.zip.
#
# Почему onedir, а не один .exe: onefile распаковывает DLL во временный каталог
# в %TEMP%, и антивирус (в том числе Defender) периодически блокирует свежие
# файлы — запуск падает с «Failed to load Python DLL». В папке распаковки нет.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python}"
export PYTHONIOENCODING=utf-8

echo "== 1/5 выгрузка баланса =="
"$PY" tools/export_balance.py

echo "== 2/5 самопроверка логики =="
"$PY" tools/selftest.py | tail -2

echo "== 3/5 сборка игры (PyInstaller, onedir) =="
"$PY" -m PyInstaller --noconfirm --clean mathidle.spec

echo "== 4/5 сборка сервера аккаунтов отдельной программой =="
"$PY" -m PyInstaller --noconfirm --clean server.spec
# Сервер кладём ВНУТРЬ папки игры: иначе он останется за пределами архива,
# и игрок, скачавший только игру, не сможет зарегистрироваться.
rm -rf dist/MathIdle/MathIdleServer
cp -r dist/MathIdleServer dist/MathIdle/MathIdleServer
rm -rf dist/MathIdle/MathIdleServer/__pycache__
cp "$ROOT/Сервер аккаунтов.txt" dist/MathIdle/ 2>/dev/null || true

echo "== 5/5 проверка собранного exe и упаковка =="
rm -f dist/MathIdle/mathidle-selftest.txt
SDL_VIDEODRIVER=dummy "$ROOT/dist/MathIdle/MathIdle.exe" --selftest || true
if [ -f dist/MathIdle/mathidle-selftest.txt ]; then
  echo "--- отчёт упакованного exe ---"
  tail -3 dist/MathIdle/mathidle-selftest.txt
else
  echo "ВНИМАНИЕ: exe не создал отчёт самопроверки"
fi
rm -f dist/MathIdle/mathidle-selftest.txt      # отчёт в релиз не нужен

# Проверяем, что собранный сервер действительно поднимается и отвечает:
# иначе игрок скачает архив, а регистрация снова не будет работать.
"$PY" - <<'PYEOF'
import os
import socket
import subprocess
import sys
import time
import urllib.request

exe = os.path.join("dist", "MathIdleServer", "MathIdleServer.exe")
if not os.path.exists(exe):
    exe = os.path.join("dist", "MathIdle", "MathIdleServer", "MathIdleServer.exe")
if not os.path.exists(exe):
    print("ВНИМАНИЕ: сервер не собран, аккаунты работать не будут")
    sys.exit(0)

with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]

proc = subprocess.Popen([exe, "--port", str(port), "--host", "127.0.0.1",
                         "--no-discovery"], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT)
ok = False
for _ in range(60):
    if proc.poll() is not None:
        break
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/health" % port, timeout=2) as resp:
            ok = resp.status == 200
        break
    except OSError:
        time.sleep(0.5)
proc.terminate()
try:
    proc.wait(timeout=10)
except subprocess.TimeoutExpired:
    proc.kill()

if ok:
    print("[ok] собранный сервер отвечает на /api/health")
else:
    out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
    print("ВНИМАНИЕ: собранный сервер не отвечает")
    print(out[-500:])
    sys.exit(1)
PYEOF

"$PY" - <<'PYEOF'
import os
import zipfile

root = os.getcwd()
dist = os.path.join(root, "dist")
src = os.path.join(dist, "MathIdle")
out = os.path.join(dist, "MathIdle-windows.zip")
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for folder, _dirs, files in os.walk(src):
        for name in files:
            full = os.path.join(folder, name)
            zf.write(full, os.path.relpath(full, dist))
print(f"[ok] {os.path.relpath(out, root)} ({os.path.getsize(out) / 1048576:.1f} МБ)")

# Проверяем, что сервер и инструкция попали внутрь: без них регистрация
# у игрока не заработает, а заметить это можно только на его компьютере.
with zipfile.ZipFile(out) as zf:
    names = set(zf.namelist())
need = ["MathIdle/MathIdleServer/MathIdleServer.exe", "MathIdle/Сервер аккаунтов.txt"]
missing = [n for n in need if n not in names]
if missing:
    print("ВНИМАНИЕ: в архиве нет " + ", ".join(missing))
    sys.exit(1)
print("[ok] сервер и инструкция внутри архива")
PYEOF

ls -la dist/
echo "== EXE ГОТОВ =="

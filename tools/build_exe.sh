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

echo "== 1/4 выгрузка баланса =="
"$PY" tools/export_balance.py

echo "== 2/4 самопроверка логики =="
"$PY" tools/selftest.py | tail -2

echo "== 3/4 сборка exe (PyInstaller, onedir) =="
"$PY" -m PyInstaller --noconfirm --clean mathidle.spec

echo "== 4/4 проверка собранного exe и упаковка =="
rm -f dist/MathIdle/mathidle-selftest.txt
SDL_VIDEODRIVER=dummy "$ROOT/dist/MathIdle/MathIdle.exe" --selftest || true
if [ -f dist/MathIdle/mathidle-selftest.txt ]; then
  echo "--- отчёт упакованного exe ---"
  tail -3 dist/MathIdle/mathidle-selftest.txt
else
  echo "ВНИМАНИЕ: exe не создал отчёт самопроверки"
fi
rm -f dist/MathIdle/mathidle-selftest.txt      # отчёт в релиз не нужен

"$PY" - <<'PYEOF'
import os
import zipfile

root = os.path.dirname(os.path.abspath("tools/build_exe.sh"))
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
PYEOF

ls -la dist/
echo "== EXE ГОТОВ =="

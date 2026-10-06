#!/usr/bin/env bash
# Собирает портативный .exe (PyInstaller, one-file) в dist/
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"
echo "== 1/3 выгрузка баланса =="
"$PY" tools/export_balance.py

echo "== 2/3 самопроверка =="
"$PY" tools/selftest.py | tail -2

echo "== 3/3 сборка exe =="
"$PY" -m PyInstaller --noconfirm --clean mathidle.spec

ls -la dist/
echo "== EXE ГОТОВ =="

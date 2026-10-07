#!/usr/bin/env bash
# Полная проверка проекта: логика, интерфейс, паритет версий, веб-тесты.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONIOENCODING=utf-8

echo "############ 1. Логика игры ############"
python tools/selftest.py | tail -4

echo ""
echo "############ 2. Интерфейс pygame ############"
python tools/render_test.py | tail -2

echo ""
echo "############ 3. Паритет Python <-> JS ############"
python tools/parity.py | tail -3

echo ""
echo "############ 4. HTML5-версия (jsdom) ############"
NODE=""
for candidate in ".toolchain/node_x24/node/node.exe" ".toolchain/node_x/node/node.exe"; do
  [ -x "$ROOT/$candidate" ] && NODE="$ROOT/$candidate" && break
done
if [ -n "$NODE" ] && [ -d "$ROOT/.toolchain/webtest/node_modules/jsdom" ]; then
  "$NODE" tools/webtest.mjs | tail -4
else
  echo "  пропущено: нет node или jsdom"
  echo "  поставить: cd .toolchain/webtest && ../node_x24/node/npm install jsdom"
fi

echo ""
echo "############ 5. Вёрстка на телефоне (настоящий браузер) ############"
bash tools/layout_check.sh | grep -E "ПРОБЛЕМ|ВСЁ ПОМЕЩАЕТСЯ|FAIL" || true

echo ""
echo "############ 6. Аккаунты (настоящий браузер) ############"
bash tools/account_check.sh | grep -E "работают|сломаны|FAIL|ПРОВАЛ|ВНИМАНИЕ|пропущен" || true

echo ""
echo "############ 7. Шифрование базы ############"
python tools/crypto_test.py | tail -2

echo ""
echo "############ 8. Зашифрованная база и сервер ############"
python tools/store_test.py | tail -2

echo ""
echo "############ Готово ############"

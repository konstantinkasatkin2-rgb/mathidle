#!/usr/bin/env bash
# Локальный сервер для браузерной версии.
#
#   bash tools/serve_web.sh          # http://localhost:8765
#   bash tools/serve_web.sh 3000     # другой порт
#
# Почему нужен сервер, а не просто открыть web/index.html: по протоколу file://
# браузер не даёт доступ к localStorage, а игра без него не сохраняет прогресс.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8765}"
cd "$ROOT/web"

echo "Math Idle — браузерная версия"
echo "  http://localhost:$PORT"
echo ""
echo "Открой адрес в браузере. Чтобы поиграть с телефона в той же сети —"
echo "  http://<IP этого компьютера>:$PORT"
echo ""
echo "Остановить: Ctrl+C"

if command -v python >/dev/null 2>&1; then
  exec python -m http.server "$PORT"
elif command -v py >/dev/null 2>&1; then
  exec py -m http.server "$PORT"
else
  exec python3 -m http.server "$PORT"
fi

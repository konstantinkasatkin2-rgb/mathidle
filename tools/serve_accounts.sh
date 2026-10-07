#!/usr/bin/env bash
# Запуск сервера аккаунтов: прогресс хранится на сервере, а не на устройстве.
#
#   bash tools/serve_accounts.sh            # http://127.0.0.1:8766
#   bash tools/serve_accounts.sh 8000       # другой порт
#   bash tools/serve_accounts.sh 8766 0.0.0.0   # доступ из локальной сети
#
# После запуска открой игру и войди в аккаунт (вкладка «Настройки»).
# Прогресс начнёт сохраняться на сервере и подтянется на другом устройстве.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8766}"
HOST="${2:-127.0.0.1}"

cd "$ROOT"
echo "Сервер аккаунтов Math Idle"
echo "  адрес: http://$HOST:$PORT"
echo "  база:  $ROOT/server/mathidle.db"
echo ""
echo "Чтобы игра на телефоне ходила на этот сервер:"
echo "  MATHIDLE_SERVER=http://<IP этого компьютера>:$PORT"
echo ""
echo "Остановить: Ctrl+C"
exec python server/account_server.py --port "$PORT" --host "$HOST"

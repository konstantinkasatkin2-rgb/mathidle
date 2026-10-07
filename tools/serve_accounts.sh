#!/usr/bin/env bash
# Запуск сервера аккаунтов: прогресс хранится на сервере, а не на устройстве.
#
#   bash tools/serve_accounts.sh                 # http://127.0.0.1:8766
#   bash tools/serve_accounts.sh 8000            # другой порт
#   bash tools/serve_accounts.sh 8766 0.0.0.0    # доступ из локальной сети
#   bash tools/serve_accounts.sh --https         # по HTTPS (нужно для сайта на HTTPS)
#
# ПОЧЕМУ НУЖЕН HTTPS: если игра открыта по HTTPS (например, сайт на GitHub
# Pages), браузер запрещает такой странице ходить на http-сервер — запрос
# падает с «Failed to fetch». Сертификат создаётся автоматически.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HTTPS=""
if [ "${1:-}" = "--https" ]; then
  HTTPS="--https"
  PORT="${2:-8766}"
  HOST="${3:-0.0.0.0}"
  if [ ! -f server/cert.pem ] || [ ! -f server/key.pem ]; then
    echo "Создаём сертификат для HTTPS…"
    bash tools/make_cert.sh localhost
  fi
else
  PORT="${1:-8766}"
  HOST="${2:-127.0.0.1}"
fi

IP="$(python - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.S_DGRAM)
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
except Exception:
    print("127.0.0.1")
finally:
    try:
        s.close()
    except Exception:
        pass
PY
)"

SCHEME="http"
[ -n "$HTTPS" ] && SCHEME="https"

echo "Сервер аккаунтов Math Idle"
echo "  здесь:  $SCHEME://127.0.0.1:$PORT"
echo "  в сети: $SCHEME://$IP:$PORT"
echo "  база:   $ROOT/server/mathidle.db"
echo ""
echo "В игре: вкладка «Настройки» → адрес сервера и «Регистрация»."
echo "С телефона указывайте адрес «в сети», а не 127.0.0.1."
if [ -n "$HTTPS" ]; then
  echo ""
  echo "Сертификат самоподписанный: браузер спросит подтверждение —"
  echo "нажмите «Всё равно перейти», иначе запрос не пройдёт."
fi
echo ""
echo "Остановить: Ctrl+C"
exec python server/account_server.py --port "$PORT" --host "$HOST" $HTTPS

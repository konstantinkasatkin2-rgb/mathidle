#!/usr/bin/env bash
# Запуск сервера аккаунтов: прогресс хранится на сервере, а не на устройстве.
#
#   bash tools/serve_accounts.sh                    # http://127.0.0.1:8766
#   bash tools/serve_accounts.sh 8000               # другой порт
#   bash tools/serve_accounts.sh 8766 0.0.0.0       # доступ из локальной сети
#   bash tools/serve_accounts.sh --https            # по HTTPS, для сайта на HTTPS
#   bash tools/serve_accounts.sh --https 8766       # другой порт для HTTPS
#
# ПОЧЕМУ НУЖЕН HTTPS: если игра открыта по HTTPS (например, сайт на GitHub
# Pages), браузер запрещает такой странице ходить на http-сервер — запрос
# падает с «Failed to fetch». Сертификат создаётся автоматически на тот адрес,
# с которого вы собираетесь заходить: с компьютера — localhost, с телефона —
# адрес в локальной сети. Если адрес не угадан, выпустите сертификат сами:
#
#   bash tools/make_cert.sh 192.168.1.10
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HTTPS=""
PORT="8766"
HOST="127.0.0.1"
CERT_CN=""

if [ "${1:-}" = "--https" ]; then
  HTTPS="--https"
  PORT="${2:-8766}"
  HOST="0.0.0.0"          # чтобы сервер был доступен и с телефона
  CERT_CN="${3:-}"
else
  PORT="${1:-8766}"
  HOST="${2:-127.0.0.1}"
fi

# Адрес компьютера в локальной сети — его указывают с телефона
lan_ip() {
  python - <<'PY'
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
}
IP="$(lan_ip)"
[ "$IP" = "127.0.0.1" ] && IP="127.0.0.1"

SCHEME="http"
if [ -n "$HTTPS" ]; then
  SCHEME="https"
  # Сертификат выпускаем на тот адрес, с которым реально придут: с телефона
  # это адрес в сети, а не localhost.
  if [ -z "$CERT_CN" ]; then
    CERT_CN="$IP"
  fi
  if [ ! -f server/cert.pem ] || [ ! -f server/key.pem ]; then
    echo "Создаём сертификат для $CERT_CN…"
    bash tools/make_cert.sh "$CERT_CN" || exit 1
  else
    echo "Сертификат уже есть: server/cert.pem"
  fi
fi

echo ""
echo "Сервер аккаунтов Math Idle"
echo "  здесь:  $SCHEME://127.0.0.1:$PORT"
echo "  в сети: $SCHEME://$IP:$PORT"
echo "  база:   $ROOT/server/mathidle.db"
echo ""
echo "В игре: вкладка «Настройки» → «Адрес сервера аккаунтов» и «Регистрация»."
echo "С телефона указывайте адрес «в сети», а не 127.0.0.1."

if [ -n "$HTTPS" ]; then
  echo ""
  echo "В игре укажите:  $SCHEME://$IP:$PORT"
  echo "Сертификат самоподписанный: браузер спросит подтверждение —"
  echo "нажмите «Всё равно перейти», иначе запрос не пройдёт."
  echo ""
  echo "Если адрес в сети другой (Wi-Fi мог дать новый), сертификат нужно"
  echo "пересоздать под него, иначе браузер его отвергнет:"
  echo "  bash tools/make_cert.sh <нужный-IP>"
fi
echo ""
echo "Остановить: Ctrl+C"
exec python server/account_server.py --port "$PORT" --host "$HOST" $HTTPS
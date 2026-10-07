#!/usr/bin/env bash
# Создаёт самоподписанный сертификат для HTTPS-сервера аккаунтов.
#
#   bash tools/make_cert.sh            # server/cert.pem + server/key.pem
#   bash tools/make_cert.sh 192.168.1.10
#
# Нужен, когда игра открыта по HTTPS (например, сайт на GitHub Pages):
# браузер не пускает такую страницу на http-сервер.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT/server"
CN="${1:-localhost}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl не найден. Поставь OpenSSL и повтори."
  exit 1
fi

MSYS_NO_PATHCONV=1 openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
  -subj "//CN=$CN" 2>/dev/null

echo "Создано:"
echo "  $CERT_DIR/cert.pem"
echo "  $CERT_DIR/key.pem"
echo ""
echo "Запуск:  bash tools/serve_accounts.sh --https"
if [ "$CN" != "localhost" ]; then
  echo "Сертификат выпущен на $CN — в игре указывайте https://$CN:8766"
fi

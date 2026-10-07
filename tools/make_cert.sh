#!/usr/bin/env bash
# Создаёт сертификат для HTTPS-сервера аккаунтов.
#
#   bash tools/make_cert.sh            # для localhost
#   bash tools/make_cert.sh 192.168.1.10   # для адреса в локальной сети
#
# Нужен, когда игра открыта по HTTPS (например, сайт на GitHub Pages):
# такая страница не может ходить на http-сервер, браузер блокирует запрос.
#
# Сертификат самоподписанный: браузер спросит подтверждение один раз.
# Чтобы он не ругался, сертификат выпущен на конкретное имя или адрес
# (поле subjectAltName), а не «на что попало».
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT/server"
CN="${1:-localhost}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl не найден. Поставь OpenSSL и повтори."
  exit 1
fi

mkdir -p "$CERT_DIR"

# Имя или адрес, на который выпускаем сертификат
if [[ "$CN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  SAN="IP:$CN"
else
  SAN="DNS:$CN"
fi

# openssl у нас — нативная программа Windows, и путь вида /d/mathidle/...
# она не понимает. MSYS2_ARG_CONV_EXCL='*' нужен, чтобы "/CN=..." не
# превратился в путь, а вот файлы передаём в виде C:\...
win_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf 'C:%s' "$(printf '%s' "$1" | sed 's|^/c|\\|; s|/|\\|g')"
  fi
}
KEY_OUT="$(win_path "$CERT_DIR/key.pem")"
CRT_OUT="$(win_path "$CERT_DIR/cert.pem")"
CRT_IN="$(win_path "$CERT_DIR/cert.pem")"
CRT_LOG="$(win_path "$CERT_DIR/.cert.log")"

MSYS2_ARG_CONV_EXCL='*' openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$KEY_OUT" -out "$CRT_OUT" \
  -subj "/CN=$CN" -addext "subjectAltName=$SAN" 2>"$CRT_LOG" || {
    echo "openssl не справился:"
    tail -3 "$CRT_LOG"
    rm -f "$CRT_LOG"
    exit 1
  }
rm -f "$CRT_LOG"

# Проверяем, что сертификат действительно годный — иначе браузер
# не признает его даже после подтверждения.
SUBJECT="$(MSYS2_ARG_CONV_EXCL='*' openssl x509 -in "$CRT_IN" -noout -subject 2>/dev/null || true)"
if [ -z "$SUBJECT" ] || [ "$SUBJECT" = "subject=" ]; then
  echo "Сертификат получился без темы — браузер его не примет."
  rm -f "$CERT_DIR/cert.pem" "$CERT_DIR/key.pem"
  exit 1
fi

echo "Создано:"
echo "  $CERT_DIR/cert.pem  ($SUBJECT)"
echo "  $CERT_DIR/key.pem"
echo ""
echo "Запуск:  bash tools/serve_accounts.sh --https"
if [ "$CN" != "localhost" ]; then
  echo "Сертификат выпущен на $CN: заходите с этого адреса."
fi
echo "Браузер спросит подтверждение сертификата — нажми «Всё равно перейти»."
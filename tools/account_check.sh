#!/usr/bin/env bash
# Проверяет аккаунты в настоящем браузере: регистрация, вход, ошибки сервера.
#
#   bash tools/account_check.sh
#
# Поднимает сервер аккаунтов на отдельной базе и отдельном порту, чтобы не
# трогать твою игру, прогоняет два сценария:
#   up   — сервер работает: регистрация, вход, неверный пароль, занятое имя
#   down — сервер выключен: игрок должен увидеть понятное объяснение,
#          а не техническое «Failed to fetch»
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8791}"
DEAD_PORT="${2:-8799}"
TMP="$(mktemp -d)"
SHOTS="$ROOT/.shots"
mkdir -p "$SHOTS"

CHROME=""
for candidate in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"; do
  [ -x "$candidate" ] && CHROME="$candidate" && break
done
if [ -z "$CHROME" ]; then
  echo "Chrome или Edge не найдены — проверка аккаунтов пропущена"
  exit 0
fi

cd "$ROOT"

# Сценарий down проверяет, что игрок видит объяснение, а не «Failed to fetch».
# Но клиент по замыслу перебирает запасные адреса из balance.js, поэтому
# сценарий имеет смысл, только когда эти порты действительно закрыты.
BUSY=""
for P in 8766 8000; do
  if netstat -ano 2>/dev/null | grep -q "127.0.0.1:$P .*LISTENING"; then
    BUSY="$BUSY $P"
  fi
done
SKIP_DOWN=""
if [ -n "$BUSY" ]; then
  echo "ВНИМАНИЕ: на портах$BUSY кто-то слушает."
  echo "Игра попробует их как запасные, поэтому сценарий «сервер недоступен»"
  echo "не сработает и будет пропущен. Остановите лишний сервер и повторите."
  SKIP_DOWN="yes"
fi

python server/account_server.py --port "$PORT" --db "$TMP/test.db" >"$TMP/server.log" 2>&1 &
SERVER_PID=$!
python -m http.server "$((PORT + 1))" >/dev/null 2>&1 &
WEB_PID=$!
cleanup() {
  kill "$SERVER_PID" "$WEB_PID" 2>/dev/null || true
  taskkill //PID "$SERVER_PID" //F >/dev/null 2>&1 || true
  taskkill //PID "$WEB_PID" //F >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT
sleep 3

echo "== проверка аккаунтов в $(basename "$CHROME") =="
STATUS=0
for MODE in up native down; do
  # в сценарии down указываем заведомо закрытый порт: сервер не отвечает
  case "$MODE" in
    up)     TARGET_PORT="$PORT" ;;
    native) TARGET_PORT="$PORT" ;;
    down)
      if [ -n "$SKIP_DOWN" ]; then
        echo ""
        echo "сценарий down — пропущен: порты$BUSY заняты"
        continue
      fi
      TARGET_PORT="$DEAD_PORT"
      ;;
  esac
  URL="http://127.0.0.1:$((PORT + 1))/tools/account_probe.html?mode=$MODE&port=$TARGET_PORT"
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --virtual-time-budget=90000 --window-size=1000,900 \
    --dump-dom "$URL" 2>/dev/null >"$TMP/$MODE.html" || true
  if ! python "$ROOT/tools/report_account.py" "$TMP/$MODE.html" "$MODE"; then
    STATUS=1
  fi
done

if [ "$STATUS" -eq 0 ]; then
  echo ""
  echo "== аккаунты работают =="
else
  echo ""
  echo "== аккаунты сломаны =="
fi
exit $STATUS
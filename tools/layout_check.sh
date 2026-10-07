#!/usr/bin/env bash
# Проверяет вёрстку игры в настоящем браузере на разных размерах экрана.
#
#   bash tools/layout_check.sh
#
# Запускает локальный сервер, открывает tools/layout_probe.html в headless
# Chrome и печатает отчёт. Ненулевой код возврата — если что-то не помещается.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8802}"
SHOTS="$ROOT/.shots"
mkdir -p "$SHOTS"

CHROME=""
for candidate in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "$LOCALAPPDATA/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"; do
  [ -x "$candidate" ] && CHROME="$candidate" && break
done
if [ -z "$CHROME" ]; then
  echo "Chrome или Edge не найдены — проверка раскладки пропущена"
  exit 0
fi

cd "$ROOT/web"
python -m http.server "$PORT" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
sleep 2

PROBE="http://127.0.0.1:$PORT/../tools/layout_probe.html"
# Chromium не любит ".." в URL — отдаём корень проекта отдельным сервером
cd "$ROOT"
python -m http.server $((PORT + 1)) >/dev/null 2>&1 &
SERVER2_PID=$!
trap 'kill $SERVER_PID $SERVER2_PID 2>/dev/null || true' EXIT
sleep 2

URL="http://127.0.0.1:$((PORT + 1))/tools/layout_probe.html"
echo "== проверка раскладки в $(basename "$CHROME") =="

RESULT="$("$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --virtual-time-budget=15000 --window-size=1400,1200 \
  --dump-dom "$URL" 2>/dev/null || true)"

# отчёт лежит в <pre id="report">
echo "$RESULT" | python -c "
import html, re, sys
data = sys.stdin.read()
m = re.search(r'<pre id=\"report\"[^>]*>(.*?)</pre>', data, re.S)
if not m:
    print('отчёт не найден — страница не отрисовалась')
    sys.exit(1)
text = html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))
print(text)
sys.exit(0 if 'ВСЁ ПОМЕЩАЕТСЯ' in text else 1)
"
STATUS=$?

# Скриншот делаем через пробник с iframe: headless Chrome не даёт окно
# уже ~500 px, поэтому --window-size=360 просто обрезает вёрстку 504 px.
# В iframe размеры точные.
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --virtual-time-budget=20000 --window-size=1400,1100 \
  --screenshot="$SHOTS/layouts.png" "$URL" >/dev/null 2>&1 || true

echo ""
echo "скриншот всех размеров: $SHOTS/layouts.png"
exit $STATUS

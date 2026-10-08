#!/usr/bin/env bash
# Собирает всё (exe + apk), публикует релиз на GitHub и скачивает его обратно.
#
#   bash tools/release.sh            # собрать, выпустить vX.Y.Z, скачать в downloads/
#   bash tools/release.sh --draft    # собрать и создать черновик, ничего не публикуя
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONIOENCODING=utf-8

VERSION=$(python -c "from mathidle import config; print(config.GAME['version'])")
TAG="v$VERSION"
DRAFT=""
[ "${1:-}" = "--draft" ] && DRAFT="--draft"

echo "===== 1. сборка Windows ====="
bash tools/build_exe.sh | tail -4

echo "===== 2. сборка Android ====="
bash tools/build_apk.sh release | tail -4

echo "===== 3. публикация релиза $TAG ====="
if gh release view "$TAG" >/dev/null 2>&1; then
  gh release delete "$TAG" --yes >/dev/null
  echo "старый релиз $TAG удалён"
fi
# Заметки — файлом, а не аргументом: текста стало столько, что командная
# строка Windows переполнилась («Argument list too long»).
NOTES_FILE="$(mktemp)"
cat tools/release-notes.md > "$NOTES_FILE"
gh release create "$TAG" \
  dist/MathIdle-windows.zip dist/MathIdle.apk \
  --title "Math Idle $TAG" \
  $DRAFT \
  --notes-file "$NOTES_FILE"
rm -f "$NOTES_FILE"

echo "===== 4. скачивание обратно ====="
mkdir -p downloads
gh release download "$TAG" --dir downloads --clobber
ls -la downloads/

echo "===== сверка ====="
for f in MathIdle-windows.zip MathIdle.apk; do
  a=$(md5sum "dist/$f" | cut -d' ' -f1)
  b=$(md5sum "downloads/$f" | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then echo "  ok   $f совпадает ($a)"; else echo "  FAIL $f: $a != $b"; exit 1; fi
done

echo "===== готово ====="
gh release view "$TAG" --json url --template '{{.url}}' 2>/dev/null || true

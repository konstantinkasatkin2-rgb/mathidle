#!/usr/bin/env bash
# Собирает Android APK из HTML5-версии (web/) через локальный тулчейн.
#
#   bash tools/build_apk.sh            # release APK (ключ создаётся автоматически)
#   bash tools/build_apk.sh debug      # debug APK (подпись отладочным ключом)
#
# Тулчейн (JDK 17 + Android SDK + Gradle) ставится в .toolchain/ скриптом
# tools/fetch_toolchain.sh — права администратора не нужны.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TC="$ROOT/.toolchain"
VARIANT="${1:-release}"

export JAVA_HOME="$TC/jdk"
export ANDROID_HOME="$TC/android-sdk"
export ANDROID_SDK_ROOT="$TC/android-sdk"
export PATH="$JAVA_HOME/bin:$TC/gradle/bin:$PATH"

if [ ! -x "$JAVA_HOME/bin/javac.exe" ] || [ ! -x "$TC/gradle/bin/gradle.bat" ]; then
  echo "Тулчейн не найден, ставлю (1-2 минуты)..."
  bash "$ROOT/tools/fetch_toolchain.sh"
fi

echo "== 1/4 выгрузка баланса =="
python "$ROOT/tools/export_balance.py"

echo "== 2/4 копирование web/ в assets/www =="
DEST="$ROOT/android/app/src/main/assets/www"
rm -rf "$ROOT/android/app/src/main/assets"
mkdir -p "$DEST"
cp "$ROOT/web/index.html" "$ROOT/web/style.css" "$ROOT/web/game.js" \
   "$ROOT/web/balance.js" "$ROOT/web/icon.png" "$DEST/"

cd "$ROOT/android"
cat > local.properties <<EOF
sdk.dir=$(cygpath -m "$ANDROID_HOME" 2>/dev/null || echo "$ANDROID_HOME")
EOF

if [ "$VARIANT" = "release" ]; then
  echo "== 3/4 ключ подписи =="
  if [ ! -f "$ROOT/android/keystore.jks" ]; then
    "$JAVA_HOME/bin/keytool" -genkeypair -v \
      -keystore "$ROOT/android/keystore.jks" \
      -storepass mathidle -keypass mathidle -alias mathidle \
      -keyalg RSA -keysize 2048 -validity 10950 \
      -dname "CN=Math Idle, OU=Game, O=Math Idle, L=Internet, C=RU" >/dev/null
    echo "создан android/keystore.jks (пароль mathidle, в .gitignore)"
  fi
  cat > keystore.properties <<EOF
storeFile=keystore.jks
storePassword=mathidle
keyAlias=mathidle
keyPassword=mathidle
EOF
else
  echo "== 3/4 debug-сборка (ключ не нужен) =="
fi

echo "== 4/4 gradle assemble${VARIANT^} =="
if [ "$VARIANT" = "release" ]; then
  gradle --no-daemon assembleRelease
  mkdir -p "$ROOT/dist"
  cp app/build/outputs/apk/release/*.apk "$ROOT/dist/MathIdle.apk"
  "$TC/android-sdk/build-tools/34.0.0/apksigner.bat" verify --print-certs \
      "$ROOT/dist/MathIdle.apk" 2>&1 | head -3
else
  gradle --no-daemon assembleDebug
  mkdir -p "$ROOT/dist"
  cp app/build/outputs/apk/debug/*.apk "$ROOT/dist/MathIdle-debug.apk"
fi

ls -la "$ROOT/dist/"
echo "== APK ГОТОВ =="

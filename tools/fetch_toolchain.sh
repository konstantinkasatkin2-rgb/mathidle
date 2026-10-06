#!/usr/bin/env bash
# Downloads the Windows toolchain needed to build the Android (WebView) APK.
# Everything is unpacked into .toolchain/ inside the project (git-ignored),
# so no administrator rights are required.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TC="$ROOT/.toolchain"
DL="$TC/dl"
mkdir -p "$DL"

get() { # url dest
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then echo "[skip] $(basename "$dest") already present"; return 0; fi
  echo "[get ] $url"
  curl -fL --retry 3 --retry-delay 5 --connect-timeout 30 -o "$dest.part" "$url" \
    && mv -f "$dest.part" "$dest" && echo "[ok  ] $(basename "$dest") $(du -h "$dest" | cut -f1)" \
    || { echo "[FAIL] $url"; rm -f "$dest.part"; return 1; }
}

unzip_to() { # zip target_dir
  local zip="$1" target="$2"
  [ -d "$target" ] && echo "[skip] $target exists" && return 0
  mkdir -p "$target"
  unzip -q -o "$zip" -d "$target" || return 1
}

# ---- JDK 17 (Temurin / Microsoft OpenJDK, portable zip) -------------------
if [ ! -x "$TC/jdk/bin/javac.exe" ]; then
  get "https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip" "$DL/jdk17.zip" \
    || get "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse" "$DL/jdk17.zip"
  rm -rf "$TC/jdk" "$TC/jdk_extract"
  unzip_to "$DL/jdk17.zip" "$TC/jdk_extract" && {
    inner="$(find "$TC/jdk_extract" -maxdepth 1 -mindepth 1 -type d | head -1)"
    mv "$inner" "$TC/jdk"
    rm -rf "$TC/jdk_extract"
  }
fi
[ -x "$TC/jdk/bin/javac.exe" ] && echo "[ok  ] JDK: $("$TC/jdk/bin/java.exe" -version 2>&1 | head -1)"

# ---- Android command line tools -----------------------------------------
if [ ! -x "$TC/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat" ]; then
  get "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" "$DL/cmdline-tools.zip"
  rm -rf "$TC/android-sdk/cmdline-tools/latest" "$TC/cmdline_extract"
  mkdir -p "$TC/android-sdk/cmdline-tools"
  unzip_to "$DL/cmdline-tools.zip" "$TC/cmdline_extract" \
    && mv "$TC/cmdline_extract/cmdline-tools" "$TC/android-sdk/cmdline-tools/latest" \
    && rm -rf "$TC/cmdline_extract"
fi
echo "[ok  ] cmdline-tools ready"

# ---- SDK packages --------------------------------------------------------
export JAVA_HOME="$TC/jdk"
export ANDROID_HOME="$TC/android-sdk"
export ANDROID_SDK_ROOT="$TC/android-sdk"
SDKMANAGER="$TC/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat"

if [ -f "$SDKMANAGER" ]; then
  yes | "$SDKMANAGER" --sdk_root="$ANDROID_HOME" --licenses >/dev/null 2>&1
  "$SDKMANAGER" --sdk_root="$ANDROID_HOME" \
      "platform-tools" "platforms;android-34" "build-tools;34.0.0" 2>&1 | tail -20
fi

# ---- Gradle --------------------------------------------------------------
if [ ! -x "$TC/gradle/bin/gradle.bat" ]; then
  get "https://services.gradle.org/distributions/gradle-8.7-bin.zip" "$DL/gradle.zip"
  rm -rf "$TC/gradle" "$TC/gradle_extract"
  unzip_to "$DL/gradle.zip" "$TC/gradle_extract" && {
    inner="$(find "$TC/gradle_extract" -maxdepth 1 -mindepth 1 -type d | head -1)"
    mv "$inner" "$TC/gradle"
    rm -rf "$TC/gradle_extract"
  }
fi
[ -x "$TC/gradle/bin/gradle.bat" ] && echo "[ok  ] Gradle present"

echo "=== TOOLCHAIN DONE ==="

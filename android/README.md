# Android-сборка Math Idle

APK собирается из HTML5-версии в `web/`: та же игра, только в WebView.

## Почему не buildozer

Обычный путь для pygame — это buildozer / python-for-android. Им нужен Linux,
WSL или Docker и права администратора. На машине, где велась разработка, не было
ни того, ни другого, ни прав — поэтому Android-версия сделана как HTML5-игра
в нативной обёртке.

Что из этого следует:

- **Плюс:** APK меньше 100 КБ, собирается на любом компьютере с JDK, без Linux.
- **Плюс:** игра полностью офлайн, ноль зависимостей и разрешений.
- **Минус:** внутри APK не Python-код, а JS. Логика общая с десктопной версией
  через общий файл баланса, тест `tools/parity.py` следит за совпадением цифр.

Когда появится машина с WSL, можно дополнительно собрать честный pygame-APK
через buildozer — `buildozer.spec` в этом репозитории для этого не готов,
но весь код на pygame лежит в `mathidle/` без изменений.

## Сборка

```bash
bash tools/fetch_toolchain.sh   # один раз: JDK 17, Android SDK 34, Gradle 8.7
bash tools/build_apk.sh         # release APK, ключ создастся сам
bash tools/build_apk.sh debug   # debug APK, ключ не нужен
```

Готовый файл: `dist/MathIdle.apk`.

## Как это устроено

`MainActivity` — единственный класс приложения:

1. Включает JavaScript и DOM-хранилище (нужно для сохранений).
2. Отдаёт файлы из `assets/www` через `shouldInterceptRequest` под домен
   `appassets.mathidle.local`.
3. Никаких зависимостей: ни AndroidX, ни Material — APK остаётся крошечным.

Домен вместо `file://` — не украшение: у страниц на `file://` в Chromium
непрозрачный origin, и `localStorage` может не работать. Со своим доменом
сохранения пишутся надёжно.

## Ключ подписи

`tools/build_apk.sh` создаёт `android/keystore.jks` (пароль `mathidle`) и
`android/keystore.properties`, если их нет. Оба файла в `.gitignore` — свой
ключ никогда не попадёт в репозиторий. Хочешь обновить приложение на телефоне
после пересборки — не удаляй `keystore.jks`, иначе Android посчитает это
другим приложением.

Если ключа нет, `assembleRelease` соберётся как debug — подпишется отладочным.

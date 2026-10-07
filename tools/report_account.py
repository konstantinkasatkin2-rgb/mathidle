"""Достаёт отчёт проверки аккаунтов из выгрузки DOM.

    python tools/report_account.py файл.html сценарий

Печатает отчёт и возвращает 0, если сценарий прошёл.
"""

import html
import re
import sys


def main() -> int:
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "?"

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = fh.read()
    except OSError as err:
        print("сценарий %s: не читается файл (%s)" % (mode, err))
        return 1

    match = re.search(r'<pre id="out"[^>]*>(.*?)</pre>', data, re.S)
    if not match:
        print("сценарий %s: отчёт не найден — страница не отрисовалась" % mode)
        return 1

    print("\nсценарий %s" % mode)
    print(html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip())

    title = re.search(r"<title>(.*?)</title>", data, re.S)
    title = title.group(1).strip() if title else ""
    if title != "ACCOUNT-OK":
        print("  ПРОВАЛ: %s" % (title or "заголовка нет"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
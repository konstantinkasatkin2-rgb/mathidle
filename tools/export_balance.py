#!/usr/bin/env python
"""Выгружает баланс из mathidle/config.py в web/balance.js и android assets.

Формат — обычный <script>, а не JSON: в Android WebView fetch() локальных
файлов блокируется политикой same-origin, а <script> работает всегда.

Запуск:
    python tools/export_balance.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mathidle import config  # noqa: E402

HEADER = (
    "/* СГЕНЕРИРОВАНО АВТОМАТИЧЕСКИ из mathidle/config.py — не редактируй руками.\n"
    " * Пересобрать: python tools/export_balance.py\n"
    " */\n"
    "var MATHIDLE_BALANCE = "
)

TARGETS = [
    os.path.join(ROOT, "web", "balance.js"),
    os.path.join(ROOT, "android", "app", "src", "main", "assets", "balance.js"),
]


def main():
    data = config.balance_dict()
    payload = HEADER + json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
    for path in TARGETS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"[ok] {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

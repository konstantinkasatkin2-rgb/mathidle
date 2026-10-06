#!/usr/bin/env python
"""Math Idle — запуск игры.

    python main.py              обычный запуск
    python main.py --selftest   проверка сборки без окна
"""

import os
import sys

SELFTEST = "--selftest" in sys.argv


def _marker_path():
    """Папка, куда можно писать отчёт: рядом с программой."""
    try:
        return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        return os.getcwd()


def _write(text, mode="w"):
    try:
        with open(os.path.join(_marker_path(), "mathidle-selftest.txt"), mode,
                  encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass


def main():
    if not SELFTEST:
        from mathidle import ui
        ui.main()
        return 0

    # в .exe консоли нет, поэтому сразу пишем отчёт в файл
    _write("Math Idle: самопроверка запущена\n")
    try:
        from mathidle import ui
        return ui.selfcheck()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — покажем, где упало
        import traceback
        _write("ОШИБКА {}: {}\n{}\n".format(type(exc).__name__, exc,
                                             traceback.format_exc()), mode="a")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

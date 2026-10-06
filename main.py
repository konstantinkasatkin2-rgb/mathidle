#!/usr/bin/env python
"""Math Idle — запуск игры.

    python main.py              обычный запуск
    python main.py --selftest   проверка сборки без окна
"""

import os
import sys
import traceback

SELFTEST = "--selftest" in sys.argv


def _log_path():
    """Папка для служебных файлов: рядом с программой."""
    folder = os.path.dirname(os.path.abspath(sys.executable))
    if not os.access(folder, os.W_OK):
        folder = os.environ.get("APPDATA") or os.getcwd()
    return os.path.join(folder, "mathidle-selftest.txt")


def _write(text, mode="a"):
    try:
        with open(_log_path(), mode, encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass


def _redirect_output():
    """В .exe без консоли sys.stdout равен None — pygame при импорте в него
    печатает приветствие и падает. Подменяем stdout/stderr файлом."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        stream = open(_log_path(), "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _excepthook(exc_type, exc, tb):
    """Пишем ошибку в файл: без консоли иначе её не увидеть."""
    _write("\nНЕОБРАБОТАННАЯ ОШИБКА\n"
           + "".join(traceback.format_exception(exc_type, exc, tb)))
    sys.__excepthook__(exc_type, exc, tb)


def main():
    _redirect_output()
    sys.excepthook = _excepthook
    if SELFTEST:
        _write("=== Math Idle: самопроверка запущена ===\n")

    if not SELFTEST:
        from mathidle import ui
        ui.main()
        return 0

    try:
        from mathidle import ui
        return ui.selfcheck()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — покажем, где упало
        _write("ОШИБКА {}: {}\n{}\n".format(type(exc).__name__, exc,
                                           traceback.format_exc()))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

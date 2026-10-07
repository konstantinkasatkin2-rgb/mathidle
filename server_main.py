"""Вход для сборки сервера аккаунтов в отдельную программу.

    python server_main.py --port 8766

Из этого файла получается MathIdleServer.exe, который лежит рядом с игрой.
Нужен, чтобы игрок, скачавший только игру, мог запустить сервер у себя
двойным щелчком, без Python и без командной строки.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "server"))

from account_server import main  # noqa: E402

if __name__ == "__main__":
    main()
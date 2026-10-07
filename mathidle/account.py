"""Клиент сервера аккаунтов: регистрация, вход, синхронизация сохранения.

Прогресс всегда лежит на устройстве. Аккаунт — это ДОПОЛНИТЕЛЬНАЯ копия,
которая позволяет продолжить игру на другом устройстве. Если сервер
недоступен, игра работает как обычно, просто без синхронизации.

Зависимостей нет: только стандартная библиотека (urllib).
"""

import json
import os
import urllib.error
import urllib.request

from . import config

TIMEOUT = 6.0


class AccountError(Exception):
    """Ошибка аккаунта, понятная игроку."""


def candidate_urls():
    """Адреса, которые пробуем по очереди."""
    urls = []
    configured = os.environ.get("MATHIDLE_SERVER", "").strip()
    if configured:
        urls.append(configured.rstrip("/"))
    default = config.ACCOUNT["default_url"].strip()
    if default:
        urls.append(default.rstrip("/"))
    else:
        # сервер поднимается скриптом tools/serve_accounts.sh рядом с игрой
        urls.extend(f"http://127.0.0.1:{port}" for port in config.ACCOUNT["fallback_ports"])
    seen, out = set(), []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _request(url, method="GET", payload=None, token=None, timeout=TIMEOUT):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


class AccountClient:
    """Тонкая обёртка над REST-API сервера аккаунтов."""

    def __init__(self, url=None):
        self.url = url
        self.username = None
        self.token = None
        self.last_error = None

    # ------------------------------------------------------------------
    @property
    def signed_in(self):
        return bool(self.token and self.username)

    def _url(self, path):
        base = self.url or (candidate_urls() or [""])[0]
        return base.rstrip("/") + path

    def _try_urls(self, path, **kwargs):
        """Пробует каждый известный адрес: сервер может быть не запущен."""
        errors = []
        for base in ([self.url] if self.url else candidate_urls()):
            try:
                self.url = base
                return _request(self._url(path), **kwargs)
            except urllib.error.HTTPError as exc:
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                except Exception:
                    body = {}
                message = body.get("error") or f"HTTP {exc.code}"
                if exc.code in (400, 401, 403, 409):      # ответ сервера — не пробуем дальше
                    raise AccountError(message) from exc
                errors.append(f"{base}: {message}")
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                errors.append(f"{base}: {exc}")
            except ValueError as exc:
                errors.append(f"{base}: неверный ответ ({exc})")
        self.last_error = "; ".join(errors) or "нет доступных адресов"
        raise AccountError(f"Сервер недоступен ({self.last_error})")

    # ------------------------------------------------------------------
    def ping(self):
        """Сервер отвечает?"""
        return bool(self._try_urls("/api/health"))

    def register(self, username, password):
        data = self._try_urls("/api/register", method="POST",
                              payload={"username": username, "password": password})
        self.username = data.get("username", username)
        self.token = data.get("token")
        return self

    def login(self, username, password):
        data = self._try_urls("/api/login", method="POST",
                              payload={"username": username, "password": password})
        self.username = data.get("username", username)
        self.token = data.get("token")
        return self

    def logout(self):
        self.username = None
        self.token = None

    def download_save(self):
        """Сохранение с аккаунта (или None, если его ещё нет)."""
        data = self._try_urls("/api/save", token=self.token)
        return data.get("save")

    def upload_save(self, save):
        self._try_urls("/api/save", method="PUT", token=self.token, payload={"save": save})
        return True

    def leaderboard(self, limit=20):
        data = self._try_urls("/api/leaderboard", timeout=4.0)
        return data.get("entries", [])

    def status(self):
        """Куда игра ходит за синхронизацией (для панели настроек)."""
        return self.url or "(не подключено)"

"""Клиент сервера аккаунтов: регистрация, вход, синхронизация сохранения.

Прогресс всегда лежит на устройстве. Аккаунт — это ДОПОЛНИТЕЛЬНАЯ копия,
которая позволяет продолжить игру на другом устройстве. Если сервер
недоступен, игра работает как обычно, просто без синхронизации.

Зависимостей нет: только стандартная библиотека (urllib).
"""

import json
import os
import re
import socket
import urllib.error
import urllib.request

from . import config

TIMEOUT = 6.0

# Почта — основной способ регистрации, поэтому проверяем её строже,
# чем имя: одна почта равна одному аккаунту, а опечатка обернётся потерей
# доступа к прогрессу навсегда.
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def normalize_email(raw):
    """Почта в едином виде: без пробелов и целиком в нижнем регистре.

    « Vasya@Mail.RU » и «vasya@mail.ru» должны считаться одним адресом,
    иначе правило «одна почта — один аккаунт» обходится регистром.
    Формально по стандарту часть до @ регистрозависима, но на практике
    провайдеры регистр не различают.
    """
    return str(raw or "").strip().strip("<>").strip().lower()


def valid_email(raw):
    """Похоже ли на адрес электронной почты."""
    text = normalize_email(raw)
    return bool(EMAIL_RE.match(text)) and len(text) <= 254


def name_from_email(email):
    """Имя для показа берём из почты: до @, без мусора."""
    local = normalize_email(email).split("@", 1)[0]
    local = re.sub(r"[^A-Za-z0-9_.-]+", "", local)[:20]
    return local or "player"


class AccountError(Exception):
    """Ошибка аккаунта, понятная игроку."""


def explain_network_error(base, exc):
    """Переводит системную ошибку сети на понятный игроку текст.

    Без этого игрок видит «<urlopen error [WinError 10061] Подключение не
    установлено…» — и не понимает, что делать.
    """
    reason = getattr(exc, "reason", None)
    text = str(reason if reason is not None else exc).lower()

    if isinstance(reason, ConnectionRefusedError) or "10061" in text \
            or "connection refused" in text or "подключение не установлено" in text:
        return f"{base}: сервер не запущен"
    if isinstance(reason, socket.timeout) or "timed out" in text or "10060" in text \
            or "превышен интервал" in text:
        return f"{base}: не отвечает (проверь, что он запущен)"
    if isinstance(reason, socket.gaierror) or "name or service not known" in text \
            or "не найден" in text:
        return f"{base}: адрес не найден"
    if "10051" in text or "сеть недоступна" in text:
        return f"{base}: сеть недоступна"
    return f"{base}: {reason if reason is not None else exc}"


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
        self.email = None
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
                errors.append(explain_network_error(base, exc))
            except ValueError as exc:
                errors.append(f"{base}: неверный ответ ({exc})")

        # Все адреса молчат. Чаще всего это просто «сервер не запущен» —
        # говорим об этом прямо, а не перечисляем системные коды.
        self.last_error = "; ".join(errors) or "нет доступных адресов"
        if errors and all("не запущен" in e or "не отвечает" in e for e in errors):
            raise AccountError(
                "Сервер аккаунтов не запущен. Открой MathIdleServer.exe "
                "в папке игры — или bash tools/serve_accounts.sh, если игра "
                "запущена из исходников."
            )
        raise AccountError(f"Сервер недоступен. Проверено: {self.last_error}")

    # ------------------------------------------------------------------
    def ping(self):
        """Сервер отвечает?

        Это проверка, а не действие: она вызывается при каждой отрисовке
        панели, поэтому молча отвечает False, а не кидает исключение.
        """
        try:
            self._try_urls("/api/health")
            return True
        except AccountError:
            return False

    def register(self, email, password, compensated=False):
        """Регистрация по почте: на одну почту — один аккаунт.

        compensated=True — компенсация уже получена на устройстве, серверу
        письмо повторно слать не надо.
        """
        data = self._try_urls("/api/register", method="POST",
                              payload={"email": email, "password": password,
                                       "compensated": bool(compensated)})
        self.username = data.get("username", "")
        self.email = data.get("email", email)
        self.token = data.get("token")
        return self

    def login(self, email, password, compensated=False):
        data = self._try_urls("/api/login", method="POST",
                              payload={"email": email, "password": password,
                                       "compensated": bool(compensated)})
        self.username = data.get("username", "")
        self.email = data.get("email", "")
        self.token = data.get("token")
        return self

    def logout(self):
        self.username = None
        self.email = None
        self.token = None

    # ------------------------------------------------------------------
    # Почта
    # ------------------------------------------------------------------
    def mail(self):
        """Письма игрока и срок их жизни (считает сервер)."""
        data = self._try_urls("/api/mail", token=self.token)
        return data.get("letters", []), data.get("unread", 0)

    def claim_mail(self, mail_id):
        """Забирает награду за письмо. Второй раз сервер не даст."""
        data = self._try_urls("/api/mail/claim", method="POST", token=self.token,
                              payload={"id": mail_id})
        return data.get("reward", 0.0)

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

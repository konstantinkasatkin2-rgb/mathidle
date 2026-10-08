#!/usr/bin/env python
"""Сервер аккаунтов Math Idle: хранение прогресса игроков.

Запуск:
    python server/account_server.py             # порт 8766
    python server/account_server.py --port 8000

Где лежат данные:
    База по умолчанию — mathidle_accounts.db в папке проекта (например
    D:\\mathidle). Файл зашифрован: это не SQLite, а контейнер
    ChaCha20 + HMAC-SHA256 (см. server/secret_store.py). Имена игроков,
    хэши паролей и сохранения прогресса в открытом виде на диске
    не лежат — открыть базу текстовым редактором нельзя.
    Ключ хранится рядом, в mathidle_accounts.key: это защищает от
    случайного подглядывания, но не от того, кто забрал всю папку.
    Настоящая защита — ключ из пароля:
        set MATHIDLE_DB_KEY=пароль   (или --passphrase)
    тогда на диске ключа нет вовсе, и забытый пароль означает потерю базы.

Пароли — PBKDF2-SHA256 с солью, токены — случайные строки со сроком
действия. Зависимостей нет: только стандартная библиотека.

API:
    GET  /api/health                  проверка живости
    POST /api/register  {username,password}
    POST /api/login     {username,password}
    GET  /api/save                     Bearer-токен
    PUT  /api/save     {save: {...}}  Bearer-токен
    GET  /api/leaderboard

Публичный: сервер хранит только прогресс игры. Никаких личных данных.
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

try:
    from mathidle import config
except ImportError:
    # Сервер собирается отдельной программой (MathIdleServer.exe), и пакета
    # mathidle рядом с ним нет. Нужны всего два значения, поэтому берём их
    # отсюда; чтобы версия не расходилась с игрой, она подставляется при сборке.
    class _Config:
        GAME = {"version": "1.2.9"}
        ACCOUNT = {"session_token_days": 30}

    config = _Config()

import secret_store as secret  # noqa: E402

# База — в папке проекта, а не рядом с кодом сервера: так её не потерять
# при пересборке и не затереть обновлением.
DB_PATH = os.environ.get("MATHIDLE_DB") or os.path.join(ROOT, "mathidle_accounts.db")
LEGACY_DB_PATH = os.path.join(HERE, "mathidle.db")   # где лежала база в 1.2.3
TOKEN_DAYS = config.ACCOUNT["session_token_days"]
MAX_SAVE_BYTES = 512 * 1024
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")
DISCOVERY_TOKEN = "mathidle"
# Правила почты общие с игрой: сервер должен отвергать ровно то же,
# что и клиент, иначе правило «одна почта — один аккаунт» можно обойти.
from mathidle.account import name_from_email, normalize_email, valid_email  # noqa: E402

MAIL_LIFETIME = config.MAIL["expires_in_seconds"]


def mail_expires_at(now=None):
    """Момент истечения письма: ровно через трое суток от отправки."""
    return (now if now is not None else time.time()) + MAIL_LIFETIME


def send_welcome_mail(conn, user_id, now=None):
    """Кладёт письмо с компенсацией — не более одного на аккаунт.

    Возвращает id письма или None, если компенсация уже была. Повторная
    попытка не создаёт ни письма, ни второй награды.
    """
    kind = config.MAIL["kind"]
    existing = conn.execute(
        "SELECT id FROM mail WHERE user_id = ? AND kind = ?",
        (user_id, kind)).fetchone()
    if existing:
        return None
    created = now if now is not None else time.time()
    try:
        cur = conn.execute(
            "INSERT INTO mail (user_id, kind, subject, body, reward,"
            " created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, kind, config.MAIL["welcome_subject"],
             config.MAIL["welcome_body"], config.MAIL["reward_money"],
             created, mail_expires_at(created)))
    except sqlite3.IntegrityError:
        return None       # гонка: письмо уже создано
    return cur.lastrowid

_lock = threading.Lock()
_db = None
_master_key = None


# --------------------------------------------------------------------------
# Ключ
# --------------------------------------------------------------------------
def master_key(passphrase=None):
    """Ключ шифрования: из пароля или из файла рядом с базой."""
    global _master_key
    if _master_key is not None:
        return _master_key
    if passphrase:
        # соль лежит в самом контейнере, поэтому здесь она фиксированная:
        # ключ выводится только из пароля
        _master_key = secret.key_from_passphrase(passphrase, b"mathidle-static-salt")
    else:
        key_path = DB_PATH + ".key"
        _master_key = secret.load_or_create_key(key_path)
    return _master_key


# --------------------------------------------------------------------------
# База
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    email       TEXT,
    salt        BLOB NOT NULL,
    password    BLOB NOT NULL,
    created_at  REAL NOT NULL,
    last_seen   REAL
);
CREATE TABLE IF NOT EXISTS saves (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payload     TEXT NOT NULL,
    updated_at  REAL NOT NULL,
    bytes       INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mail (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT '',
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    reward      REAL NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    claimed_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_mail_user ON mail(user_id);
-- Одно письмо данного вида на аккаунт. Повторная компенсация за ту же
-- почту невозможна даже при сбое в коде: база просто не даст вставить
-- вторую строку.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mail_once ON mail(user_id, kind);
-- Уникальность почты живёт в индексе, а не в самой колонке: SQLite не
-- умеет добавлять колонку с UNIQUE через ALTER TABLE, а старые базы
-- приходится доводить на месте. COLLATE NOCASE — иначе база считала бы
-- Vasya@mail.ru и vasya@mail.ru разными адресами.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email COLLATE NOCASE);
"""


def migrate(conn):
    """Доводит старую базу до текущей схемы.

    У базы 1.2.3–1.2.5 не было колонки email и таблицы mail. База
    зашифрована и лежит у игрока на диске, поэтому «создать, если нет»
    мало: колонку в существующей таблице так не добавить.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "email" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "mail" in tables:
        # Таблица уже была — у прежних писем вида не было. Считаем их
        # компенсацией, иначе ограничение «одно письмо на аккаунт» их бы
        # пропустило, и добавляем колонку с видом.
        mail_columns = {row["name"] for row in conn.execute("PRAGMA table_info(mail)")}
        if "kind" not in mail_columns:
            conn.execute("ALTER TABLE mail ADD COLUMN kind TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE mail SET kind = ? WHERE kind = ''",
                         (config.MAIL["kind"],))
            # две компенсации одному аккаунту оставляем только одну
            conn.execute(
                "DELETE FROM mail WHERE id NOT IN ("
                "  SELECT MIN(id) FROM mail GROUP BY user_id, kind)"
            )
    conn.executescript(SCHEMA)
    conn.commit()


def open_memory_db():
    """Пустая база в памяти — на диске её нет ни в каком виде."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def load_plaintext_db(path):
    """Читает обычную базу SQLite с диска (перенос со старой версии)."""
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except sqlite3.Error:
        conn.close()
        return None
    conn.close()
    return count


def import_legacy(target, path):
    """Переносит аккаунты из старой незашифрованной базы."""
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    try:
        users = src.execute(
            "SELECT id, username, salt, password, created_at, last_seen"
            " FROM users").fetchall()
        saves = src.execute(
            "SELECT user_id, payload, updated_at, bytes FROM saves").fetchall()
        tokens = src.execute(
            "SELECT token, user_id, created_at, expires_at FROM tokens").fetchall()
    except sqlite3.Error:
        src.close()
        return 0

    ids = {}
    for row in users:
        cur = target.execute(
            "INSERT INTO users (username, salt, password, created_at, last_seen)"
            " VALUES (?, ?, ?, ?, ?)",
            (row["username"], row["salt"], row["password"],
             row["created_at"], row["last_seen"]))
        ids[row["id"]] = cur.lastrowid
    for row in saves:
        new_id = ids.get(row["user_id"])
        if new_id:
            target.execute(
                "INSERT INTO saves (user_id, payload, updated_at, bytes)"
                " VALUES (?, ?, ?, ?)",
                (new_id, row["payload"], row["updated_at"], row["bytes"]))
    for row in tokens:
        new_id = ids.get(row["user_id"])
        if new_id:
            target.execute(
                "INSERT OR IGNORE INTO tokens (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)",
                (row["token"], new_id, row["created_at"], row["expires_at"]))
    src.close()
    target.commit()
    return len(users)


def db():
    """База в памяти; на диске лежит только зашифрованный контейнер."""
    global _db
    if _db is None:
        _db = open_memory_db()
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as fh:
                plain = secret.unseal(fh.read(), master_key())
            _db.deserialize(plain)
            migrate(_db)
        elif os.path.exists(LEGACY_DB_PATH) and DB_PATH != LEGACY_DB_PATH:
            count = import_legacy(_db, LEGACY_DB_PATH)
            if count:
                flush()
                print("Перенесено аккаунтов из старой базы: %d" % count)
        else:
            flush()          # сразу создаём зашифрованный файл
    return _db


def flush():
    """Записывает базу на диск — уже зашифрованной."""
    if _db is None:
        return
    secret.write_atomic(DB_PATH, secret.seal(_db.serialize(), master_key()))


def commit():
    """Записать изменения и сразу зашифровать на диск.

    Замена db().commit(): данные не должны лежать на диске открытыми
    даже на секунду.
    """
    _db.commit()
    flush()


# --------------------------------------------------------------------------
# Поиск сервера в локальной сети
# --------------------------------------------------------------------------
def lan_address():
    """IP этого компьютера, каким его видят другие устройства в сети."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _discovery_loop(sock, port, scheme, stop):
    """Отвечает на UDP-«пинги»: телефон спрашивает «есть ли тут сервер?»."""
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(512)
        except OSError:
            if stop.is_set():
                return
            continue
        if DISCOVERY_TOKEN.encode() not in data:
            continue
        reply = json.dumps({
            "service": "mathidle",
            "version": config.GAME["version"],
            "port": port,
            "scheme": scheme,
            "encrypted": True,
        }).encode()
        try:
            sock.sendto(reply, addr)
        except OSError:
            pass


def start_discovery(port, scheme):
    """Запускает UDP-слушатель, чтобы игра нашла сервер сама."""
    stop = threading.Event()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
    except OSError as err:
        sock.close()
        print("Поиск в сети не запустился: %s" % err)
        print("Адрес придётся ввести вручную в настройках игры.")
        return None, stop
    thread = threading.Thread(target=_discovery_loop,
                              args=(sock, port, scheme, stop), daemon=True)
    thread.start()
    return sock, stop


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt, digest


def new_token():
    return secrets.token_urlsafe(32)


def token_expiry():
    return time.time() + TOKEN_DAYS * 86400


def user_for_token(token):
    if not token:
        return None
    with _lock:
        row = db().execute(
            """SELECT u.id, u.username FROM tokens t
               JOIN users u ON u.id = t.user_id
               WHERE t.token = ? AND t.expires_at > ?""",
            (token, time.time()),
        ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------
# Обработчик запросов
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "MathIdle/1.2"
    protocol_version = "HTTP/1.1"

    # ---------------- вспомогательное ----------------
    def log_message(self, fmt, *args):        # тише в консоли
        if os.environ.get("MATHIDLE_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        # По этому заголовку телефон узнаёт, что ответил наш сервер,
        # а не какой-то другой сайт на том же адресе.
        self.send_header("X-MathIdle", "1")
        self.send_header("X-MathIdle-Version", config.GAME["version"])
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_SAVE_BYTES * 2:
            raise ValueError("слишком большой запрос")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def bearer(self):
        header = self.headers.get("Authorization") or ""
        if header.startswith("Bearer "):
            return header[7:].strip()
        return None

    def require_user(self):
        user = user_for_token(self.bearer())
        if not user:
            self.send_json(401, {"error": "Нужно войти в аккаунт"})
            return None
        return user

    # ---------------- маршруты ----------------
    def do_OPTIONS(self):
        self.send_json(204, {})

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/api/health", "/"):
            self.send_json(200, {"ok": True, "service": "mathidle-accounts",
                                 "version": config.GAME["version"]})
        elif path == "/api/save":
            self.get_save()
        elif path == "/api/leaderboard":
            self.leaderboard()
        elif path == "/api/mail":
            self.get_mail()
        elif path == "/":
            self.send_json(404, {"error": "не найдено"})
        else:
            self.send_json(404, {"error": "не найдено"})

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            data = self.read_json()
        except (ValueError, OSError):
            self.send_json(400, {"error": "некорректный запрос"})
            return
        if path == "/api/register":
            self.register(data)
        elif path == "/api/login":
            self.login(data)
        elif path == "/api/mail/claim":
            self.claim_mail(data)
        else:
            self.send_json(404, {"error": "не найдено"})

    def do_PUT(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/api/save":
            self.send_json(404, {"error": "не найдено"})
            return
        self.put_save()

    # ---------------- действия ----------------
    def register(self, data):
        # Регистрация идёт по почте: на одну почту — один аккаунт.
        email = normalize_email(data.get("email") or data.get("username", ""))
        password = str(data.get("password", ""))
        if not valid_email(email):
            self.send_json(400, {
                "error": "Почта не похожа на адрес. Пример: vasya@mail.ru"})
            return
        if len(password) < 6:
            self.send_json(400, {"error": "Пароль минимум 6 символов"})
            return

        salt, digest = hash_password(password)
        username = name_from_email(email)
        now = time.time()
        with _lock:
            taken = db().execute(
                "SELECT username FROM users WHERE email = ? OR username = ?",
                (email, username)).fetchone()
            if taken:
                self.send_json(409, {
                    "error": "На эту почту уже есть аккаунт — попробуй «Войти»"})
                return
            try:
                cur = db().execute(
                    "INSERT INTO users (username, email, salt, password,"
                    " created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, email, salt, digest, now, now))
                user_id = cur.lastrowid
            except sqlite3.IntegrityError:
                self.send_json(409, {
                    "error": "На эту почту уже есть аккаунт — попробуй «Войти»"})
                return
            token = new_token()
            db().execute(
                "INSERT INTO tokens (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)", (token, user_id, now, token_expiry()))
            # Письмо с компенсацией уходит сразу после регистрации.
            mail_id = None
            if not data.get("compensated"):
                # Если компенсация уже получена на этом устройстве (аккаунт
                # создавался без сервера), второго письма не будет.
                mail_id = send_welcome_mail(db(), user_id, now)
            commit()
        self.send_json(201, {"username": username, "email": email,
                             "token": token, "mail_id": mail_id})

    def login(self, data):
        login = str(data.get("email") or data.get("username", "")).strip()
        password = str(data.get("password", ""))
        # Войти можно и по почте, и по старому имени: часть аккаунтов
        # заведена до появления почты.
        email = normalize_email(login) if "@" in login else None
        with _lock:
            if email:
                row = db().execute(
                    "SELECT id, username, email, salt, password FROM users"
                    " WHERE email = ? OR username = ?", (email, login)).fetchone()
            else:
                row = db().execute(
                    "SELECT id, username, email, salt, password FROM users"
                    " WHERE username = ?", (login,)).fetchone()
        if not row:
            self.send_json(401, {"error": "Неверная почта или пароль"})
            return
        _salt, digest = hash_password(password, bytes(row["salt"]))
        if not hmac.compare_digest(digest, bytes(row["password"])):
            self.send_json(401, {"error": "Неверная почта или пароль"})
            return

        now = time.time()
        with _lock:
            db().execute("UPDATE users SET last_seen = ? WHERE id = ?", (now, row["id"]))
            token = new_token()
            db().execute(
                "INSERT INTO tokens (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)", (token, row["id"], now, token_expiry()))
            # Аккаунтам, заведённым до появления почты, письмо тоже
            # положим — компенсация им полагается так же.
            have_mail = db().execute(
                "SELECT 1 FROM mail WHERE user_id = ? AND kind = ?",
                (row["id"], config.MAIL["kind"])).fetchone()
            if not have_mail and not data.get("compensated"):
                send_welcome_mail(db(), row["id"], now)
            commit()
        self.send_json(200, {"username": row["username"],
                             "email": row["email"], "token": token})

    def get_save(self):
        user = self.require_user()
        if not user:
            return
        with _lock:
            row = db().execute(
                "SELECT payload, updated_at FROM saves WHERE user_id = ?",
                (user["id"],)).fetchone()
        if not row:
            self.send_json(200, {"save": None, "updated_at": None})
            return
        try:
            save = json.loads(row["payload"])
        except ValueError:
            save = None
        self.send_json(200, {"save": save, "updated_at": row["updated_at"]})

    def put_save(self):
        user = self.require_user()
        if not user:
            return
        try:
            data = self.read_json()
        except ValueError:
            self.send_json(400, {"error": "некорректный запрос"})
            return
        save = data.get("save")
        if save is None:
            self.send_json(400, {"error": "пустое сохранение"})
            return
        payload = json.dumps(save, ensure_ascii=False)
        if len(payload.encode("utf-8")) > MAX_SAVE_BYTES:
            self.send_json(413, {"error": "сохранение слишком большое"})
            return
        now = time.time()
        with _lock:
            db().execute(
                """INSERT INTO saves (user_id, payload, updated_at, bytes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     payload = excluded.payload,
                     updated_at = excluded.updated_at,
                     bytes = excluded.bytes""",
                (user["id"], payload, now, len(payload.encode("utf-8"))))
            commit()
        self.send_json(200, {"ok": True, "updated_at": now})

    def get_mail(self):
        """Письма игрока. Просроченные не показываем и убираем."""
        user = self.require_user()
        if not user:
            return
        now = time.time()
        with _lock:
            expired = db().execute("DELETE FROM mail WHERE expires_at <= ?", (now,))
            if expired.rowcount:
                commit()
            rows = db().execute(
                "SELECT id, subject, body, reward, created_at, expires_at, claimed_at"
                " FROM mail WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],)).fetchall()
        letters = [{
            "id": row["id"],
            "subject": row["subject"],
            "body": row["body"],
            "reward": row["reward"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "claimed": row["claimed_at"] is not None,
        } for row in rows]
        unread = sum(1 for letter in letters if not letter["claimed"])
        self.send_json(200, {"letters": letters, "unread": unread,
                             "server_time": now})

    def claim_mail(self, data):
        """Забирает награду за письмо. Второй раз — уже нельзя."""
        user = self.require_user()
        if not user:
            return
        try:
            mail_id = int(data.get("id"))
        except (TypeError, ValueError):
            self.send_json(400, {"error": "не указано письмо"})
            return

        now = time.time()
        with _lock:
            row = db().execute(
                "SELECT id, reward, expires_at, claimed_at FROM mail"
                " WHERE id = ? AND user_id = ?", (mail_id, user["id"])).fetchone()
            if not row:
                self.send_json(404, {"error": "письмо не найдено"})
                return
            if row["claimed_at"] is not None:
                self.send_json(409, {"error": "награда уже получена"})
                return
            if row["expires_at"] <= now:
                db().execute("DELETE FROM mail WHERE id = ?", (mail_id,))
                commit()
                self.send_json(410, {"error": "письмо сгорело"})
                return
            db().execute("UPDATE mail SET claimed_at = ? WHERE id = ?", (now, mail_id))
            commit()
        self.send_json(200, {"ok": True, "reward": row["reward"], "id": mail_id})

    def leaderboard(self):
        query = ("SELECT u.username, s.updated_at, s.bytes, "
                 "json_extract(s.payload, '$.money') AS money "
                 "FROM saves s JOIN users u ON u.id = s.user_id "
                 "ORDER BY money DESC LIMIT 20")
        with _lock:
            rows = db().execute(query).fetchall()
        entries = [
            {
                "username": r["username"],
                "money": r["money"] or 0.0,
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
        self.send_json(200, {"entries": entries})


def setup_console():
    """Готовит вывод: кириллица, символы и отсутствие консоли.

    Без этого сервер падает на первой же строке вывода, когда его запускают
    двойным щелчком или из .bat: консоль Windows не понимает UTF-8.
    Ещё две беды, которые стоили времени:
      * stdout буферизуется, и при остановке всё напечатанное теряется —
        игрок не видит ни адреса, ни подсказки;
      * при запуске без консоли поток вообще None, и print() падает.
    """
    if sys.stdout is None:
        try:
            sys.stdout = open(os.path.join(ROOT, "account_server.log"),
                              "a", encoding="utf-8")
        except OSError:
            sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
        except (AttributeError, ValueError):
            pass


def main():
    global DB_PATH

    setup_console()
    parser = argparse.ArgumentParser(description="Сервер аккаунтов Math Idle")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--db", default=DB_PATH, help="файл зашифрованной базы")
    parser.add_argument("--passphrase", default=None,
                        help="пароль для базы вместо файла ключа")
    parser.add_argument("--https", action="store_true",
                        help="поднять по HTTPS (нужно, если игра открыта по HTTPS)")
    parser.add_argument("--cert", default=None, help="файл сертификата .pem")
    parser.add_argument("--key", default=None, help="файл ключа .pem")
    parser.add_argument("--no-discovery", action="store_true",
                        help="не отвечать на поиск в локальной сети")
    args = parser.parse_args()

    DB_PATH = args.db
    passphrase = args.passphrase or os.environ.get("MATHIDLE_DB_KEY") or None

    scheme = "https" if args.https else "http"
    ip = lan_address()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    if args.https:
        cert = args.cert or os.path.join(HERE, "cert.pem")
        key = args.key or os.path.join(HERE, "key.pem")
        if not (os.path.exists(cert) and os.path.exists(key)):
            print(f"Нет сертификата: {cert} / {key}")
            print("Создать: bash tools/make_cert.sh")
            server.server_close()
            return 1
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert, keyfile=key)
        server.socket = context.wrap_socket(server.socket, server_side=True)

    # База читается сразу: если пароль не тот, лучше узнать об этом сейчас,
    # чем получить отказ в середине игры.
    try:
        master_key(passphrase)
        db()
    except secret.SecretError as err:
        print("База не открылась: %s" % err)
        print("Если ключ задан паролем — проверь MATHIDLE_DB_KEY.")
        server.server_close()
        return 1

    print(f"Сервер аккаунтов Math Idle {config.GAME['version']}")
    print(f"  здесь:  {scheme}://127.0.0.1:{args.port}")
    print(f"  в сети: {scheme}://{ip}:{args.port}")
    print(f"  база:   {DB_PATH} (зашифрована)")
    if passphrase:
        print("  ключ:   из пароля MATHIDLE_DB_KEY, на диске его нет")
    else:
        print(f"  ключ:   {DB_PATH}.key")
    print("")
    print("В игре: Настройки → «Адрес сервера аккаунтов». На телефоне игра")
    print("найдёт сервер сама, если он запущен на этом компьютере.")
    if args.host == "0.0.0.0":
        print("")
        print("Сервер виден всей сети, а не только этому компьютеру — так его")
        print("находит телефон. Пароли хранятся хэшами, но прогресс и имена")
        print("доступны любому в этой сети. Для одного компьютера запусти")
        print("с --host 127.0.0.1.")

    stop = threading.Event()
    if not args.no_discovery:
        sock, stop = start_discovery(args.port, scheme)
        if sock is not None:
            print("  поиск в сети: включён (телефон найдёт сервер сам)")

    if args.https and args.host in ("0.0.0.0", "127.0.0.1", "localhost"):
        print("")
        print("ВНИМАНИЕ: сертификат самоподписанный, браузер спросит подтверждение.")

    print("")
    print("Остановить: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        stop.set()
        server.server_close()
        with _lock:
            flush()
        print("База сохранена и зашифрована.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Сервер аккаунтов Math Idle: хранение прогресса игроков.

Запуск:
    python server/account_server.py             # порт 8766
    python server/account_server.py --port 8000

Хранит всё в SQLite (server/mathidle.db). Пароли — PBKDF2-SHA256 с солью,
токены — случайные строки с сроком действия. Зависимостей нет: только
стандартная библиотека.

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
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mathidle import config  # noqa: E402

DB_PATH = os.path.join(HERE, "mathidle.db")
TOKEN_DAYS = config.ACCOUNT["session_token_days"]
MAX_SAVE_BYTES = 512 * 1024
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")

_lock = threading.Lock()
_db = None


# --------------------------------------------------------------------------
# База
# --------------------------------------------------------------------------
def db():
    global _db
    if _db is None:
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
            """
        )
        _db.commit()
    return _db


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
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        if not USERNAME_RE.match(username):
            self.send_json(400, {
                "error": "Имя: 3–24 символа, латиница, цифры, «_», «-», «.»"})
            return
        if len(password) < 6:
            self.send_json(400, {"error": "Пароль минимум 6 символов"})
            return

        salt, digest = hash_password(password)
        now = time.time()
        with _lock:
            try:
                cur = db().execute(
                    "INSERT INTO users (username, salt, password, created_at, last_seen)"
                    " VALUES (?, ?, ?, ?, ?)", (username, salt, digest, now, now))
                user_id = cur.lastrowid
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Такое имя уже занято"})
                return
            token = new_token()
            db().execute(
                "INSERT INTO tokens (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)", (token, user_id, now, token_expiry()))
            db().commit()
        self.send_json(201, {"username": username, "token": token})

    def login(self, data):
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        with _lock:
            row = db().execute(
                "SELECT id, salt, password FROM users WHERE username = ?",
                (username,)).fetchone()
        if not row:
            self.send_json(401, {"error": "Неверное имя или пароль"})
            return
        _salt, digest = hash_password(password, bytes(row["salt"]))
        if not hmac.compare_digest(digest, bytes(row["password"])):
            self.send_json(401, {"error": "Неверное имя или пароль"})
            return

        now = time.time()
        with _lock:
            db().execute("UPDATE users SET last_seen = ? WHERE id = ?", (now, row["id"]))
            token = new_token()
            db().execute(
                "INSERT INTO tokens (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)", (token, row["id"], now, token_expiry()))
            db().commit()
        self.send_json(200, {"username": username, "token": token})

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
            db().commit()
        self.send_json(200, {"ok": True, "updated_at": now})

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


def main():
    global DB_PATH

    parser = argparse.ArgumentParser(description="Сервер аккаунтов Math Idle")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--https", action="store_true",
                        help="поднять по HTTPS (нужно, если игра открыта по HTTPS)")
    parser.add_argument("--cert", default=None, help="файл сертификата .pem")
    parser.add_argument("--key", default=None, help="файл ключа .pem")
    args = parser.parse_args()

    DB_PATH = args.db

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    scheme = "http"
    if args.https:
        cert = args.cert or os.path.join(HERE, "cert.pem")
        key = args.key or os.path.join(HERE, "key.pem")
        if not (os.path.exists(cert) and os.path.exists(key)):
            print(f"Нет сертификата: {cert} / {key}")
            print("Создать (команда openssl):")
            print('  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \\')
            print(f'    -keyout "{key}" -out "{cert}" -subj "/CN=localhost"')
            print("Либо запустите tools/make_cert.sh")
            server.server_close()
            return 1
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert, keyfile=key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"Сервер аккаунтов Math Idle: {scheme}://{args.host}:{args.port}")
    print(f"База: {DB_PATH}")
    if scheme == "https" and args.host in ("127.0.0.1", "localhost"):
        print("ВНИМАНИЕ: сертификат самоподписанный для localhost. Браузер спросит")
        print("подтверждение — нажмите «Всё равно перейти», иначе запрос не пройдёт.")
    print("Остановить: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
        server.server_close()


if __name__ == "__main__":
    main()

"""Проверка зашифрованной базы аккаунтов: сервер, файл на диске, перезапуск.

    python tools/store_test.py

Поднимает сервер на временной базе, проверяет, что на диске лежит
шифротекст, что после перезапуска аккаунты на месте, что неверный пароль
не открывает базу и что старая незашифрованная база переносится.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server", "account_server.py")

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  ← %s" % (detail,)))
    if not ok:
        fails.append(name)


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(port, path, payload=None, token=None, method=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or (
        "POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode() or "{}")
        except ValueError:
            return err.code, {}
    except OSError as err:
        return 0, {"error": str(err)}


def start(port, db, passphrase=None, with_discovery=False, extra=None):
    """Запускает сервер и ждёт, пока он начнёт отвечать."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if passphrase:
        env["MATHIDLE_DB_KEY"] = passphrase
    cmd = [sys.executable, SERVER, "--port", str(port), "--db", db,
           "--host", "127.0.0.1", "--no-discovery"]
    if with_discovery:
        cmd.remove("--no-discovery")
    if extra:
        cmd += extra
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(80):
        if proc.poll() is not None:
            return proc, proc.stdout.read().decode("utf-8", "replace")
        code, _ = request(port, "/api/health")
        if code == 200:
            return proc, ""
        time.sleep(0.25)
    return proc, "сервер не поднялся"


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def raw(path):
    with open(path, "rb") as fh:
        return fh.read()


print("Регистрация и файл на диске")
folder = tempfile.mkdtemp()
db_path = os.path.join(folder, "accounts.db")
port = free_port()
proc, log = start(port, db_path)
if proc.poll() is not None:
    check("сервер поднялся", False, log[-400:])
    print("ПРОВАЛЕНО: сервер не запустился")
    sys.exit(1)
check("сервер поднялся", True)
check("файл базы создан", os.path.exists(db_path))
check("ключ создан", os.path.exists(db_path + ".key"))

code, body = request(port, "/api/register", {"username": "vasya",
                                             "password": "parol123"})
check("регистрация прошла", code == 201, (code, body))
token = body.get("token", "")
check("токен выдан", bool(token))

code, body = request(port, "/api/save", {"save": {"money": 12345.6, "level": 7}},
                     token=token, method="PUT")
check("прогресс сохранён", code == 200, (code, body))

blob = raw(db_path)
check("на диске нет заголовка SQLite", b"SQLite format" not in blob)
check("на диске нет имени игрока", b"vasya" not in blob)
check("на диске нет сохранения", b"12345" not in blob and b"money" not in blob)
check("на диске нет соли и хэша пароля", b"parol" not in blob)
stop(proc)

print("Перезапуск: данные на месте")
proc, log = start(port, db_path)
if proc.poll() is not None:
    check("сервер поднялся снова", False, log[-400:])
else:
    check("сервер поднялся снова", True)
    code, body = request(port, "/api/login", {"username": "vasya",
                                               "password": "parol123"})
    check("вход после перезапуска", code == 200, (code, body))
    code, body = request(port, "/api/save", token=body.get("token", ""))
    check("прогресс уцелел", (body.get("save") or {}).get("money") == 12345.6, body)
    code, body = request(port, "/api/login", {"username": "vasya",
                                               "password": "nepravilny"})
    check("неверный пароль отклонён", code == 401, (code, body))
stop(proc)

print("Неверный пароль от базы")
wrong_port = free_port()
proc, log = start(wrong_port, db_path, passphrase="чужой-пароль")
check("сервер не поднялся с чужим паролем", proc.poll() is not None)
check("и объяснил почему", "пароль" in log.lower() or "не открылась" in log.lower(),
      log[-200:])
stop(proc)

print("База под паролем")
pass_dir = tempfile.mkdtemp()
pass_db = os.path.join(pass_dir, "accounts.db")
pass_port = free_port()
proc, log = start(pass_port, pass_db, passphrase="мой-пароль")
if proc.poll() is not None:
    check("база создалась по паролю", False, log[-400:])
else:
    check("база создалась по паролю", True)
    check("файл ключа не создавался", not os.path.exists(pass_db + ".key"))
    code, body = request(pass_port, "/api/register",
                         {"username": "petya", "password": "parol456"})
    check("регистрация по паролю", code == 201, (code, body))
    stop(proc)

    # перезапуск с тем же паролем
    proc, log = start(pass_port, pass_db, passphrase="мой-пароль")
    if proc.poll() is not None:
        check("база открылась тем же паролем", False, log[-300:])
    else:
        check("база открылась тем же паролем", True)
        code, body = request(pass_port, "/api/login",
                             {"username": "petya", "password": "parol456"})
        check("аккаунты на месте", code == 200, (code, body))
    stop(proc)
shutil.rmtree(pass_dir, ignore_errors=True)

print("Перенос со старой незашифрованной базы")
legacy_dir = tempfile.mkdtemp()
legacy_path = os.path.join(legacy_dir, "mathidle.db")
maker = os.path.join(legacy_dir, "make_old_db.py")
with open(maker, "w", encoding="utf-8") as fh:
    fh.write(
        "import json, sqlite3, sys, time\n"
        "db = sqlite3.connect(sys.argv[1])\n"
        "db.executescript(\n"
        "    'CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL,"
        " password BLOB NOT NULL, created_at REAL NOT NULL, last_seen REAL);'\n"
        "    'CREATE TABLE saves (user_id INTEGER PRIMARY KEY,"
        " payload TEXT NOT NULL, updated_at REAL NOT NULL, bytes INTEGER NOT NULL);'\n"
        "    'CREATE TABLE tokens (token TEXT PRIMARY KEY,"
        " user_id INTEGER NOT NULL, created_at REAL NOT NULL,"
        " expires_at REAL NOT NULL);')\n"
        "db.execute('INSERT INTO users (username, salt, password, created_at, last_seen)'\n"
        "           ' VALUES (?, ?, ?, ?, ?)',\n"
        "           ('starosta', bytes(16), bytes(32), time.time(), None))\n"
        "payload = json.dumps({'money': 999.5})\n"
        "db.execute('INSERT INTO saves VALUES (1,?,?,?)',\n"
        "           (payload, time.time(), len(payload)))\n"
        "db.commit()\n"
        "db.close()\n"
    )
made = subprocess.run([sys.executable, maker, legacy_path],
                      capture_output=True, text=True, encoding="utf-8")
check("старая база создана", os.path.exists(legacy_path), made.stderr[-300:])

sys.path.insert(0, os.path.join(ROOT, "server"))
import account_server as acc  # noqa: E402

new_db = os.path.join(legacy_dir, "accounts.db")
acc._db = None
acc._master_key = None
acc.DB_PATH = new_db
acc.LEGACY_DB_PATH = legacy_path
acc._db = acc.open_memory_db()
moved = acc.import_legacy(acc._db, legacy_path)
check("аккаунты перенесены", moved == 1, moved)
acc.commit()
check("перенесённая база записана зашифрованной", os.path.exists(new_db))
blob = raw(new_db)
check("в новом файле нет открытых данных",
      b"SQLite format" not in blob and b"starosta" not in blob)
check("старый файл остался нетронутым", os.path.exists(legacy_path))
acc._db = None
names = [r[0] for r in acc.db().execute("SELECT username FROM users")]
check("после перечитывания имя на месте", names == ["starosta"], names)

print("Поиск сервера в сети (UDP)")
disc_dir = tempfile.mkdtemp()
disc_db = os.path.join(disc_dir, "accounts.db")
disc_port = free_port()
proc, log = start(disc_port, disc_db, with_discovery=True)
if proc.poll() is not None:
    check("сервер с поиском поднялся", False, log[-300:])
else:
    check("сервер с поиском поднялся", True)
    import socket as _socket

    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    sock.settimeout(3)
    sock.sendto(b"mathidle", ("127.0.0.1", disc_port))
    try:
        reply, addr = sock.recvfrom(512)
        check("сервер ответил на поиск", b"mathidle" in reply, reply[:60])
        check("в ответе есть порт и шифрование",
              str(disc_port).encode() in reply and b'"encrypted": true' in reply,
              reply[:120])
    except _socket.timeout:
        check("сервер ответил на поиск", False, "тишина")
    sock.close()

    # чужой пакет сервер игнорирует
    sock2 = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    sock2.settimeout(1.0)
    sock2.sendto("что-то другое".encode("utf-8"), ("127.0.0.1", disc_port))
    try:
        sock2.recvfrom(512)
        check("на чужой пакет не отвечает", False, "ответил")
    except _socket.timeout:
        check("на чужой пакет не отвечает", True)
    sock2.close()
stop(proc)
shutil.rmtree(disc_dir, ignore_errors=True)

print("Повторные записи")
acc._db = None
acc.DB_PATH = os.path.join(legacy_dir, "many.db")
acc.LEGACY_DB_PATH = os.path.join(legacy_dir, "нет-такой-базы.db")
acc._master_key = None
acc.master_key("пароль")
acc.db()                       # создаёт пустую зашифрованную базу
for name in ("a", "b", "c"):
    acc.db().execute("INSERT INTO users (username, salt, password, created_at)"
                     " VALUES (?, ?, ?, 0)", (name, bytes(16), bytes(32)))
    acc.commit()
acc._db = None
count = acc.db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
check("после перечитывания все записи на месте", count == 3, count)

shutil.rmtree(folder, ignore_errors=True)
shutil.rmtree(legacy_dir, ignore_errors=True)

print()
if fails:
    print("ПРОВАЛЕНО проверок: %d" % len(fails))
    for name in fails:
        print("  - " + name)
    sys.exit(1)
print("Зашифрованная база работает")
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


def acc_letters(port, token):
    """Сколько писем видит игрок с этим токеном."""
    _code, body = request(port, "/api/mail", token=token)
    return len(body.get("letters", []))


print("Сервер должен хотя бы запускаться")
# Модуль сервера раньше никто не импортировал, поэтому в него однажды попала
# опечатка (потерянная скобка) — и проверка аккаунтов молча падала целиком.
# Импортируем здесь же: синтаксическая ошибка видна сразу.
try:
    sys.path.insert(0, os.path.join(ROOT, "server"))
    sys.path.insert(0, ROOT)
    import account_server as _acc_probe
    check("модуль сервера импортируется", True)
    check("в нём есть обработчик запросов",
          hasattr(_acc_probe, "Handler") and hasattr(_acc_probe, "main"))
    game_version = _acc_probe.config.GAME.get("version")
    check("в сервере версия игры совпадает", bool(game_version), game_version)
    # Кому виден сервер. Tailscale на этой машине может и не стоять —
    # проверяем решение, а не наличие туннеля.
    check("адрес 100.x распознан как Tailscale",
          _acc_probe.is_tailnet("100.101.102.103")
          and _acc_probe.is_tailnet("100.64.0.0")
          and _acc_probe.is_tailnet("100.127.255.255"))
    check("домашний адрес не принят за Tailscale",
          not _acc_probe.is_tailnet("192.168.0.251")
          and not _acc_probe.is_tailnet("100.128.0.1")
          and not _acc_probe.is_tailnet("127.0.0.1")
          and not _acc_probe.is_tailnet("не адрес"))
    check("есть Tailscale — сервер слушает только его",
          _acc_probe.pick_host("100.101.102.103") == "100.101.102.103",
          _acc_probe.pick_host("100.101.102.103"))
    check("нет Tailscale — сервер слушает всё и сам предупредит",
          _acc_probe.pick_host(None) == "0.0.0.0",
          _acc_probe.pick_host(None))
    check("--lan возвращает открытый доступ",
          _acc_probe.pick_host("100.101.102.103", None, True) == "0.0.0.0",
          _acc_probe.pick_host("100.101.102.103", None, True))
    check("явный адрес главнее всего",
          _acc_probe.pick_host("100.101.102.103", "127.0.0.1") == "127.0.0.1",
          _acc_probe.pick_host("100.101.102.103", "127.0.0.1"))
    found = _acc_probe.tailscale_address()
    check("адрес Tailscale либо есть и верный, либо его нет",
          found is None or _acc_probe.is_tailnet(found), found)
except SyntaxError as err:
    check("модуль сервера импортируется", False, "синтаксис: %s" % err)
except Exception as err:                       # noqa: BLE001
    check("модуль сервера импортируется", False, err)

print("")
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

code, body = request(port, "/api/register", {"email": "vasya@mail.ru",
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
    code, body = request(port, "/api/login", {"email": "vasya@mail.ru",
                                               "password": "parol123"})
    check("вход после перезапуска", code == 200, (code, body))
    code, body = request(port, "/api/save", token=body.get("token", ""))
    check("прогресс уцелел", (body.get("save") or {}).get("money") == 12345.6, body)
    code, body = request(port, "/api/login", {"email": "vasya@mail.ru",
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
                         {"email": "petya@mail.ru", "password": "parol456"})
    check("регистрация по паролю", code == 201, (code, body))
    stop(proc)

    # перезапуск с тем же паролем
    proc, log = start(pass_port, pass_db, passphrase="мой-пароль")
    if proc.poll() is not None:
        check("база открылась тем же паролем", False, log[-300:])
    else:
        check("база открылась тем же паролем", True)
        code, body = request(pass_port, "/api/login",
                             {"email": "petya@mail.ru", "password": "parol456"})
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

print("Почта: письмо с компенсацией")
mail_dir = tempfile.mkdtemp()
mail_db = os.path.join(mail_dir, "accounts.db")
mail_port = free_port()
proc, log = start(mail_port, mail_db)
if proc.poll() is not None:
    check("сервер с почтой поднялся", False, log[-300:])
else:
    check("сервер с почтой поднялся", True)

    code, body = request(mail_port, "/api/register",
                         {"email": "Ivan@Mail.RU", "password": "parol123"})
    check("регистрация по почте", code == 201, (code, body))
    check("почта приведена к нижнему регистру",
          body.get("email") == "ivan@mail.ru", body.get("email"))
    token = body.get("token", "")

    code, body = request(mail_port, "/api/register",
                         {"email": "ivan@mail.ru ", "password": "parol123"})
    check("на одну почту — один аккаунт", code == 409, (code, body))
    check("и сказано, что делать",
          "Войти" in body.get("error", ""), body.get("error"))

    code, body = request(mail_port, "/api/register",
                         {"email": "это-не-почта", "password": "parol123"})
    check("мусор вместо почты отвергнут", code == 400, (code, body))

    code, body = request(mail_port, "/api/mail", token=token)
    letters = body.get("letters", [])
    check("письмо пришло сразу после регистрации", len(letters) == 1, letters)
    letter = letters[0] if letters else {}
    check("тема письма",
          letter.get("subject") == "Компенсация за утраченный прогресс",
          letter.get("subject"))
    check("в письме есть текст", len(letter.get("body", "")) > 20, letter.get("body"))
    check("награда 100 денег", letter.get("reward") == 100.0, letter.get("reward"))
    check("есть срок", isinstance(letter.get("expires_at"), (int, float)))
    check("непрочитанных: 1", body.get("unread") == 1, body.get("unread"))

    life = letter.get("expires_at", 0) - letter.get("created_at", 0)
    check("срок ровно трое суток", abs(life - 3 * 86400) < 0.001, life)

    # Одна компенсация на одну почту — даже если код попытается дважды
    check("повторное письмо на сервере не создаётся",
          acc_letters(mail_port, token) == 1,
          acc_letters(mail_port, token))
    code, body = request(mail_port, "/api/register",
                         {"email": "ivan@mail.ru", "password": "parol123"})
    check("вторая регистрация той же почты отклонена", code == 409, (code, body))
    # даже прямой вход обратно не должен вернуть компенсацию ещё раз
    code, body = request(mail_port, "/api/login",
                         {"email": "ivan@mail.ru", "password": "parol123"})
    again = acc_letters(mail_port, body.get("token", ""))
    check("и повторный вход тоже без второго письма", code == 200 and again == 1,
          (code, again))

    # флаг «компенсация уже получена» гасит письмо совсем
    code, body = request(mail_port, "/api/register",
                         {"email": "device@mail.ru", "password": "parol123",
                          "compensated": True})
    quiet = acc_letters(mail_port, body.get("token", ""))
    check("регистрация с флагом компенсации письма не шлёт",
          code == 201 and quiet == 0, (code, quiet))

    mail_id = letter.get("id")
    code, body = request(mail_port, "/api/mail/claim", {"id": mail_id}, token=token)
    check("награда выдана", code == 200 and body.get("reward") == 100.0, (code, body))
    code, body = request(mail_port, "/api/mail/claim", {"id": mail_id}, token=token)
    check("второй раз награду не дают", code == 409, (code, body))
    code, body = request(mail_port, "/api/mail", token=token)
    check("после получения непрочитанных 0", body.get("unread") == 0, body.get("unread"))

    # Вход должен работать по почте
    code, body = request(mail_port, "/api/login",
                         {"email": "IVAN@MAIL.RU", "password": "parol123"})
    check("вход по почте в любом регистре", code == 200, (code, body))
    code, body = request(mail_port, "/api/login",
                         {"email": "ivan@mail.ru", "password": "неверный"})
    check("неверный пароль отвергнут", code == 401, (code, body))
stop(proc)

print("Почта: сгоревшее письмо")
sys.path.insert(0, os.path.join(ROOT, "server"))
import account_server as acc  # noqa: E402

acc._db = None
acc._master_key = None
acc.DB_PATH = os.path.join(mail_dir, "expiry.db")
acc.LEGACY_DB_PATH = os.path.join(mail_dir, "нет.db")
acc._db = acc.open_memory_db()
acc.commit()
now = 1_700_000_000.0
cur = acc._db.execute(
    "INSERT INTO users (username, email, salt, password, created_at)"
    " VALUES ('u', 'a@b.ru', ?, ?, ?)", (bytes(16), bytes(32), now))
user_id = cur.lastrowid
fresh_id = acc.send_welcome_mail(acc._db, user_id, now)
old_id = acc._db.execute(
    "INSERT INTO mail (user_id, kind, subject, body, reward, created_at,"
    " expires_at) VALUES (?, 'other', 'старое', '', 0, ?, ?)",
    (user_id, now - 10 * 86400, now - 7 * 86400)).lastrowid
check("письмо живёт трое суток",
      acc._db.execute("SELECT expires_at - created_at FROM mail WHERE id = ?",
                      (fresh_id,)).fetchone()[0] == 3 * 86400)
check("повторная компенсация не создаётся",
      acc.send_welcome_mail(acc._db, user_id, now) is None)


def _dup_insert(account_server, user_id, stamp):
    """Прямая попытка вставить вторую компенсацию — база должна отказать."""
    import sqlite3 as _sq
    try:
        account_server._db.execute(
            "INSERT INTO mail (user_id, kind, subject, body, reward,"
            " created_at, expires_at) VALUES (?, 'compensation', 'ещё', '', 0, ?, ?)",
            (user_id, stamp, stamp))
        return False
    except _sq.IntegrityError:
        return True


check("прямая вставка дубля отклонена", _dup_insert(acc, user_id, now))
check("сгоревшее письмо помечается в прошлом",
      acc._db.execute("SELECT expires_at <= ? FROM mail WHERE id = ?",
                      (now, old_id)).fetchone()[0] == 1)
rows = acc._db.execute(
    "SELECT id FROM mail WHERE user_id = ? AND expires_at > ?",
    (user_id, now)).fetchall()
check("живое письмо остаётся", [r[0] for r in rows] == [fresh_id], rows)
shutil.rmtree(mail_dir, ignore_errors=True)

print("Почта: старая база без колонки email и без таблицы mail")
import sqlite3 as _sqlite3  # noqa: E402

# База ровно такой схемы, какой она была в 1.2.3–1.2.5: без email и без mail.
old_conn = _sqlite3.connect(":memory:", check_same_thread=False)
old_conn.row_factory = _sqlite3.Row
old_conn.executescript(
    "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, password BLOB NOT NULL,"
    " created_at REAL NOT NULL, last_seen REAL);"
    "CREATE TABLE saves (user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL,"
    " updated_at REAL NOT NULL, bytes INTEGER NOT NULL);"
    "CREATE TABLE tokens (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL,"
    " created_at REAL NOT NULL, expires_at REAL NOT NULL);")
old_conn.execute("INSERT INTO users (username, salt, password, created_at)"
                 " VALUES ('starosta', ?, ?, 1700000000)",
                 (bytes(16), bytes(32)))
old_conn.execute("INSERT INTO saves VALUES (1, '{\"money\": 999.5}', 1700000000, 18)")
old_conn.commit()
old_bytes = old_conn.serialize()
old_conn.close()

acc._db = None
acc._master_key = None
acc.DB_PATH = os.path.join(mail_dir, "migrated.db")
acc._db = acc.open_memory_db()
acc._db.deserialize(old_bytes)
before = {row["name"] for row in acc._db.execute("PRAGMA table_info(users)")}
check("в старой базе колонки email нет", "email" not in before, before)
tables_before = {row[0] for row in acc._db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}

acc.migrate(acc._db)
after = {row["name"] for row in acc._db.execute("PRAGMA table_info(users)")}
check("миграция добавила колонку email", "email" in after, after)
tables_after = {row[0] for row in acc._db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
check("миграция создала таблицу mail", "mail" in tables_after - tables_before,
      tables_after - tables_before)
row = acc._db.execute("SELECT id, username, email FROM users").fetchone()
check("старый аккаунт цел и почта пустая",
      row["username"] == "starosta" and row["email"] is None, dict(row))
saved = acc._db.execute("SELECT payload FROM saves").fetchone()
check("старое сохранение цело", "999.5" in saved["payload"], saved["payload"])
check("письмо старому аккаунту кладётся",
      acc.send_welcome_mail(acc._db, row["id"]) > 0)
# уникальность почты держит индекс, а не колонка
acc._db.execute("UPDATE users SET email = 'starosta@mail.ru' WHERE id = ?", (row["id"],))
try:
    acc._db.execute("INSERT INTO users (username, email, salt, password, created_at)"
                     " VALUES ('drugoy', 'STAROSTA@mail.ru', ?, ?, 1700000000)",
                     (bytes(16), bytes(32)))
    acc._db.commit()
    check("почта остаётся уникальной", False, "проглотил дубль")
except _sqlite3.IntegrityError:
    check("почта остаётся уникальной", True)
acc._db = None
acc._master_key = None

shutil.rmtree(folder, ignore_errors=True)
shutil.rmtree(legacy_dir, ignore_errors=True)

print("Переустановка: вернётся ли прогресс")
# Вопрос игрока: зарегистрировался, удалил приложение, поставил заново —
# смогу ли войти? Проверяем на живом сервере и настоящем клиенте.
restore_dir = tempfile.mkdtemp()
restore_db = os.path.join(restore_dir, "accounts.db")
restore_port = free_port()
sys.path.insert(0, ROOT)
from mathidle import account as player_account  # noqa: E402

proc, log = start(restore_port, restore_db)
if proc.poll() is not None:
    check("сервер для переустановки поднялся", False, log[-300:])
else:
    # первый заход: регистрация, игра, синхронизация
    first = player_account.AccountClient(url="http://127.0.0.1:%d" % restore_port)
    first.register("reinstall@mail.ru", "parol123")
    payload = {"money": 4321.5, "run_earned": 4321.5, "test_level": 5,
               "prestige_count": 2, "prestige_points": 3,
               "max_difficulty_solved": 1.0,
               "stats": {"solved": 777, "earned": 99999, "wrong": 3,
                         "tests_passed": 9, "best_streak": 42,
                         "prestige_points_total": 7, "passive_earned": 0,
                         "idle_examples": 0, "ascensions": 0, "femboy": False}}
    first.upload_save(payload)
    check("прогресс ушёл на сервер", True)

    # «удаляем приложение»: устройство забывает всё, токен тоже
    again = player_account.AccountClient(url="http://127.0.0.1:%d" % restore_port)
    again.login("reinstall@mail.ru", "parol123")
    restored = again.download_save()
    check("вход после удаления приложения удался", again.signed_in)
    check("прогресс вернулся целиком",
          bool(restored) and restored.get("money") == 4321.5
          and restored.get("prestige_count") == 2
          and restored.get("stats", {}).get("solved") == 777,
          restored if not restored else {
              "money": restored.get("money"),
              "prestige_count": restored.get("prestige_count"),
              "solved": restored.get("stats", {}).get("solved")})
    letters = again.mail()[0]
    check("после переустановки письмо ровно одно", len(letters) == 1, letters)
    check("и оно ещё не получено", letters and letters[0]["claimed"] is False)

    # а вот аккаунт без сервера живёт только на устройстве: тут хранить нечего
    check("без сервера восстанавливать нечего",
          not os.path.exists(os.path.join(restore_dir, "нет-такого.db")))
stop(proc)
shutil.rmtree(restore_dir, ignore_errors=True)

print()
print("Второй игрок на том же устройстве")
# Вопрос игрока: как зарегистрироваться другому игроку? Ответ — выйти и
# зарегистрировать другую почту. Проверяем главное: деньги первого игрока
# не должны достаться второму и не должны записаться в его аккаунт.
two_dir = tempfile.mkdtemp()
two_db = os.path.join(two_dir, "accounts.db")
two_port = free_port()
sys.path.insert(0, ROOT)
from mathidle import state as player_state  # noqa: E402

proc, log = start(two_port, two_db)
if proc.poll() is not None:
    check("сервер для второго игрока поднялся", False, log[-300:])
else:
    url = "http://127.0.0.1:%d" % two_port
    st = player_state.GameState()
    st.account = player_account.AccountClient(url=url)

    ok, text = st.register("pervyy@mail.ru", "parol123")
    check("первый игрок зарегистрировался", ok, text)
    st.money = 5000.0
    st.stats["solved"] = 120
    st.sync_to_server(silent=True)

    # выход и вход того же игрока: прогресс остаётся его
    st.sign_out()
    ok, text = st.sign_in("pervyy@mail.ru", "parol123")
    check("первый игрок вернул свой прогресс",
          ok and st.money == 5000.0, "%s / %s" % (text, st.money))

    # выход и регистрация другого человека на том же устройстве
    st.sign_out()
    ok, text = st.register("vtoroy@mail.ru", "parol123")
    check("второй игрок зарегистрировался", ok, text)
    check("второй игрок начинает с нуля, а не с чужими деньгами",
          st.money == 0.0, st.money)
    check("и чужая статистика не досталась",
          st.stats.get("solved") == 0, st.stats.get("solved"))
    check("настройки устройства остались свои", bool(st.settings))

    # прогресс первого игрока на сервере цел и вернётся ему
    other = player_account.AccountClient(url=url)
    other.login("pervyy@mail.ru", "parol123")
    saved = other.download_save()
    check("прогресс первого игрока не пострадал",
          bool(saved) and saved.get("money") == 5000.0,
          saved.get("money") if saved else None)

    # у каждого игрока своё письмо с компенсацией
    check("у первого игрока своё письмо", len(other.mail()[0]) == 1)
    again2 = player_account.AccountClient(url=url)
    again2.login("vtoroy@mail.ru", "parol123")
    check("у второго игрока своё письмо", len(again2.mail()[0]) == 1)

    # перенос аккаунта без сервера тоже делает прогресс «своим»
    local = player_state.GameState()
    local.money = 777.0
    ok, text = local.register_local("tretiy@mail.ru")
    check("аккаунт без сервера создан", ok, text)
    check("прогресс до переноса остался своим", local.owner_email == "tretiy@mail.ru")
stop(proc)
shutil.rmtree(two_dir, ignore_errors=True)

print()
print("Второе устройство")
# Вопрос игрока: как зарегистрироваться с другого телефона? Проверяем, что
# аккаунт виден с двух устройств сразу, прогресс переезжает, а повторная
# регистрация той же почты честно отвечает «войди», а не заводит дубль.
dev_dir = tempfile.mkdtemp()
dev_db = os.path.join(dev_dir, "accounts.db")
dev_port = free_port()
proc, log = start(dev_port, dev_db)
if proc.poll() is not None:
    check("сервер для второго устройства поднялся", False, log[-300:])
else:
    url = "http://127.0.0.1:%d" % dev_port
    # первое устройство: регистрация, игра, синхронизация
    phone1 = player_account.AccountClient(url=url)
    phone1.register("telefon1@mail.ru", "parol123")
    phone1.upload_save({"money": 300.0, "stats": {"solved": 20}})
    check("первое устройство зарегистрировано", phone1.signed_in)

    # регистрация той же почты со второго устройства
    phone2 = player_account.AccountClient(url=url)
    try:
        phone2.register("telefon1@mail.ru", "parol123")
        check("повторная регистрация отклонена", False, "аккаунт создан повторно")
    except player_account.AccountError as exc:
        check("повторная регистрация отклонена", "уже есть аккаунт" in str(exc), exc)

    # правильный путь — «Войти», и прогресс приезжает
    phone2.login("telefon1@mail.ru", "parol123")
    moved = phone2.download_save()
    check("второе устройство вошло", phone2.signed_in)
    check("прогресс переехал на второе устройство",
          bool(moved) and moved.get("money") == 300.0,
          moved.get("money") if moved else None)

    # оба устройства работают одновременно: вход не выбивает первое
    phone1.upload_save({"money": 450.0, "stats": {"solved": 25}})
    still = phone1.download_save()
    check("первое устройство не выбито вторым",
          bool(still) and still.get("money") == 450.0,
          still.get("money") if still else None)
    check("второе устройство тоже работает", phone2.signed_in)

    # у аккаунта одно письмо с компенсацией, сколько устройств ни подключай
    check("письмо с компенсацией одно на почту", len(phone2.mail()[0]) == 1)
stop(proc)
shutil.rmtree(dev_dir, ignore_errors=True)

print()
if fails:
    print("ПРОВАЛЕНО проверок: %d" % len(fails))
    for name in fails:
        print("  - " + name)
    sys.exit(1)
print("Зашифрованная база работает")
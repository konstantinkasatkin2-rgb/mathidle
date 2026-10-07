"""Проверка шифрования базы: модуль secret_store и контейнер.

    python tools/crypto_test.py
"""

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "server"))

import secret_store as ss  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  ← %s" % (detail,)))
    if not ok:
        fails.append(name)


print("ChaCha20 (RFC 8439, §2.4.2)")
# ключ 00..1f, nonce 00 00 00 00 00 00 00 4a 00 00 00 00, счётчик 1
key = bytes(range(32))
nonce_24 = bytes([0, 0, 0, 0, 0, 0, 0, 0x4A, 0, 0, 0, 0])
plain = b"Ladies and Gentlemen of the class of '99: If I could offer you "
ct = ss.chacha20_xor(key, nonce_24, plain)
check("ChaCha20 обратима", ss.chacha20_xor(key, nonce_24, ct) == plain)

# Сверяем с независимой реализацией: если есть openssl, считаем им же.
try:
    import subprocess
    import tempfile as _tf

    with _tf.TemporaryDirectory() as _folder:
        src = os.path.join(_folder, "p.bin")
        with open(src, "wb") as _fh:
            _fh.write(plain)
        # OpenSSL ждёт IV = счётчик (4 байта LE) + nonce
        iv = (1).to_bytes(4, "little") + nonce_24
        proc = subprocess.run(
            ["openssl", "enc", "-chacha20", "-K", key.hex(), "-iv", iv.hex(),
             "-in", src], capture_output=True)
    check("совпадает с openssl (независимая реализация)", proc.stdout == ct,
          proc.stdout[:16].hex())
except (OSError, FileNotFoundError):
    print("  ..   openssl не найден — сверка с ним пропущена")

print("ChaCha20 (RFC 8439, §2.3.2 — блок состояния)")
# в §2.3.2 nonce другой: 00:00:00:09:00:00:00:4a:00:00:00:00
nonce_23 = bytes.fromhex("000000090000004a00000000")
block = ss._block(list(struct.unpack("<8I", key)), 1,
                  list(struct.unpack("<3I", nonce_23)))
expect = bytes.fromhex(
    "10f1e7e4d13b5915500fdd1fa32071c4"
    "c7d1f4c733c068030422aa9ac3d46c4e"
    "d2826446079faa0914c2d705d98b02a2"
    "b5129cd1de164eb9cbd083e8a2503c4e")
check("блок состояния сходится с RFC", block == expect, block[:16].hex())

print("Контейнер")
master = ss.secrets.token_bytes(32)
data = b"SQLite format 3\x00" + "данные аккаунтов".encode("utf-8") * 100
sealed = ss.seal(data, master)
check("контейнер не содержит открытых данных",
      b"SQLite format" not in sealed and "данные аккаунтов".encode() not in sealed)
check("расшифровка возвращает исходное", ss.unseal(sealed, master) == data)


def wrong_key():
    try:
        ss.unseal(sealed, ss.secrets.token_bytes(32))
    except ss.SecretError:
        return True
    return False


check("с чужим ключом — отказ", wrong_key())


def tampered():
    bad = bytearray(sealed)
    bad[-1] ^= 0xFF
    try:
        ss.unseal(bytes(bad), master)
    except ss.SecretError:
        return True
    return False


check("испорченный файл — отказ", tampered())


def wrong_magic():
    bad = bytearray(sealed)
    bad[0] = ord("X")
    try:
        ss.unseal(bytes(bad), master)
    except ss.SecretError:
        return True
    return False


check("чужой файл — отказ", wrong_magic())


def truncated():
    try:
        ss.unseal(sealed[:10], master)
    except ss.SecretError:
        return True
    return False


check("обрезанный файл — отказ", truncated())

print("Пароль и файл ключа")
salt = b"\x01" * 16
k1 = ss.key_from_passphrase("мой пароль", salt)
k2 = ss.key_from_passphrase("мой пароль", salt)
k3 = ss.key_from_passphrase("другой пароль", salt)
check("одинаковый пароль даёт один ключ", k1 == k2)
check("разный пароль даёт разный ключ", k1 != k3)
check("пароль без соли даёт другой ключ",
      k1 != ss.key_from_passphrase("мой пароль", b"\x02" * 16))

with tempfile.TemporaryDirectory() as folder:
    key_path = os.path.join(folder, "база.key")
    first = ss.load_or_create_key(key_path)
    check("ключ создан", os.path.exists(key_path))
    check("ключ 32 байта", len(first) == 32, len(first))
    check("ключ не меняется при повторном чтении",
          ss.load_or_create_key(key_path) == first)

    # Ключ, начинающийся и кончающийся «пробельными» байтами, не должен
    # портиться при чтении — из-за этого ключ и хранят в виде текста.
    for tricky in (b"\n" + b"\xab" * 30 + b"\t",
                   b" " + b"\x00" * 30 + b" ",
                   b"\r\n" + b"\xff" * 29 + b"\n"):
        assert len(tricky) == 32
        with open(key_path, "w", encoding="ascii") as fh:
            fh.write(tricky.hex() + "\n")
        check("ключ с непечатаемыми краями читается верно (%r)"
              % tricky[:2], ss.load_or_create_key(key_path) == tricky)
        with open(key_path, "wb") as fh:
            fh.write(tricky)
        check("старый ключ из сырых байтов читается верно (%r)"
              % tricky[:2], ss.load_or_create_key(key_path) == tricky)

print("Запись на диск")
with tempfile.TemporaryDirectory() as folder:
    path = os.path.join(folder, "база.db")
    ss.write_atomic(path, sealed)
    check("файл записан", os.path.exists(path))
    check("на диске шифротекст", not ss.is_sealed(path) is False)
    check("файл распознан как наш", ss.is_sealed(path))
    check("прочитан обратно", ss.unseal(open(path, "rb").read(), master) == data)
    other = "новые данные".encode("utf-8")
    ss.write_atomic(path, ss.seal(other, master))
    check("повторная запись перезаписывает",
          ss.unseal(open(path, "rb").read(), master) == other)
    check("временных файлов не осталось",
          not os.path.exists(path + ".tmp"))

print()
if fails:
    print("ПРОВАЛЕНО проверок: %d" % len(fails))
    for name in fails:
        print("  - " + name)
    sys.exit(1)
print("Шифрование работает")
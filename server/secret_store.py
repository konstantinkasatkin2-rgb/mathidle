"""Шифрование файла базы аккаунтов.

Файл на диске — не база SQLite, а контейнер: ChaCha20 + HMAC-SHA256
(«зашифровать, потом подписать»). Подпись проверяется до расшифровки,
поэтому подделанный или испорченный файл не превращается в данные.

Зависимостей нет: только стандартная библиотека.

Мастер-ключ берётся одним из двух способов:

    * файл ключа (по умолчанию) — 32 случайных байта рядом с базой.
      Удобно, но честно: кто имеет доступ ко всей папке, получит и ключ,
      и данные. Такой ключ защищает от случайного подглядывания и от
      чужих программ, читающих файл, — но не от того, кто забрал папку целиком.
    * пароль (MATHIDLE_DB_KEY или --passphrase) — ключ выводится из пароля
      и на диске не хранится. Настоящая защита, но сервер придётся
      каждый раз запускать с этим паролем, а забытый пароль означает
      потерю всех аккаунтов.

Формат контейнера:

    magic 8 байт   b"MIDB\\x01\\x00"
    соль 16 байт
    nonce 12 байт
    подпись 32 байта
    шифротекст
"""

import hashlib
import hmac
import os
import secrets
import struct

MAGIC = b"MIDB\x01\x00"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 32
WORDS = 16   # слов в состоянии ChaCha20 (64 байта блока)


class SecretError(Exception):
    """Файл не то, чем кажется: пароль не тот или файл испорчен."""


# --------------------------------------------------------------------------
# ChaCha20 (RFC 8439)
# --------------------------------------------------------------------------
_MASK = 0xFFFFFFFF
_CONST = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)


def _quarter(x, a, b, c, d):
    x[a] = (x[a] + x[b]) & _MASK
    x[d] ^= x[a]
    x[d] = ((x[d] << 16) | (x[d] >> 16)) & _MASK
    x[c] = (x[c] + x[d]) & _MASK
    x[b] ^= x[c]
    x[b] = ((x[b] << 12) | (x[b] >> 20)) & _MASK
    x[a] = (x[a] + x[b]) & _MASK
    x[d] ^= x[a]
    x[d] = ((x[d] << 8) | (x[d] >> 24)) & _MASK
    x[c] = (x[c] + x[d]) & _MASK
    x[b] ^= x[c]
    x[b] = ((x[b] << 7) | (x[b] >> 25)) & _MASK


def _block(key_words, counter, nonce_words):
    state = list(_CONST) + key_words + [counter] + nonce_words
    work = state[:]
    for _ in range(10):                 # 20 раундов — это 10 двойных
        _quarter(work, 0, 4, 8, 12)
        _quarter(work, 1, 5, 9, 13)
        _quarter(work, 2, 6, 10, 14)
        _quarter(work, 3, 7, 11, 15)
        _quarter(work, 0, 5, 10, 15)
        _quarter(work, 1, 6, 11, 12)
        _quarter(work, 2, 7, 8, 13)
        _quarter(work, 3, 4, 9, 14)
    out = [(work[i] + state[i]) & _MASK for i in range(WORDS)]
    return struct.pack("<16I", *out)


def chacha20_xor(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """Шифрует (или расшифровывает — операция симметричная) данные."""
    if len(key) != 32:
        raise ValueError("ключ должен быть 32 байта")
    if len(nonce) != NONCE_BYTES:
        raise ValueError("nonce должен быть 12 байт")
    key_words = list(struct.unpack("<8I", key))
    nonce_words = list(struct.unpack("<3I", nonce))
    out = bytearray(len(data))
    for offset in range(0, len(data), 64):
        block = _block(key_words, offset // 64 + 1, nonce_words)
        chunk = data[offset:offset + 64]
        out[offset:offset + len(chunk)] = bytes(
            a ^ b for a, b in zip(chunk, block)
        )
    return bytes(out)


def _subkeys(master: bytes, salt: bytes):
    """Из мастер-ключа и соли получаем ключ данных и ключ подписи."""
    data_key = hmac.new(master, b"data" + salt, hashlib.sha256).digest()
    mac_key = hmac.new(master, b"mac" + salt, hashlib.sha256).digest()
    return data_key, mac_key


# --------------------------------------------------------------------------
# Мастер-ключ
# --------------------------------------------------------------------------
def load_or_create_key(path: str) -> bytes:
    """Читает файл ключа, а если его нет — создаёт новый.

    Ключ хранится в виде шестнадцатеричного текста, а не сырых байтов:
    случайный 32-байтовый ключ вполне может начинаться или кончаться
    байтом пробела или перевода строки — и при чтении «с обрезкой
    пробелов» молча испортился бы.
    """
    if os.path.exists(path):
        with open(path, "rb") as fh:
            raw = fh.read()
        text = raw.strip().decode("ascii", "ignore")
        if len(text) == 64:
            try:
                return bytes.fromhex(text)
            except ValueError:
                pass
        if len(raw) == 32:                   # ключ из старой версии, сырые байты
            return raw
        raise SecretError("файл ключа повреждён: %s" % path)

    key = secrets.token_bytes(32)
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".new"
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(key.hex() + "\n")
    os.replace(tmp, path)
    return key


def key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    """Ключ из пароля игрока. Долгий и солёный, чтобы перебор не помог."""
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), b"mathidle-db" + salt, 390_000)


# --------------------------------------------------------------------------
# Контейнер
# --------------------------------------------------------------------------
def seal(plaintext: bytes, master: bytes) -> bytes:
    """Шифрует данные и возвращает готовый контейнер."""
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    data_key, mac_key = _subkeys(master, salt)
    body = chacha20_xor(data_key, nonce, plaintext)
    head = MAGIC + salt + nonce
    tag = hmac.new(mac_key, head + body, hashlib.sha256).digest()
    return head + tag + body


def unseal(container: bytes, master: bytes) -> bytes:
    """Проверяет подпись и расшифровывает контейнер."""
    head_len = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    if len(container) < head_len + TAG_BYTES:
        raise SecretError("файл слишком короткий — это не база")
    if not container.startswith(MAGIC):
        raise SecretError("это не база Math Idle (неверная подпись файла)")
    salt = container[len(MAGIC):len(MAGIC) + SALT_BYTES]
    nonce = container[len(MAGIC) + SALT_BYTES:head_len]
    tag = container[head_len:head_len + TAG_BYTES]
    body = container[head_len + TAG_BYTES:]
    data_key, mac_key = _subkeys(master, salt)
    expected = hmac.new(mac_key, MAGIC + salt + nonce + body,
                        hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise SecretError("подпись не сходится: пароль не тот или файл испорчен")
    return chacha20_xor(data_key, nonce, body)


def write_atomic(path: str, data: bytes) -> None:
    """Записывает файл целиком, чтобы обрыв не оставил половину записи."""
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def is_sealed(path: str) -> bool:
    """Похоже ли содержимое файла на наш зашифрованный контейнер."""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False
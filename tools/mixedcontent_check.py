"""Воспроизводит ошибку «Failed to fetch»: страница по HTTPS, сервер по HTTP.

Браузер запрещает такой запрос (mixed content), и fetch падает ДО сети —
сервер не получает запрос вообще. Скрипт поднимает HTTPS-страницу с
пробником, который пытается дёрнуть http://127.0.0.1:8766 и печатает,
что именно вернул браузер.

    python tools/mixedcontent_check.py
"""

import http.server
import os
import ssl
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>mixed</title></head>
<body><pre id="out">…</pre>
<script>
var out = document.getElementById('out');
function log(s) { out.textContent += s + "\\n"; }
fetch('http://127.0.0.1:8766/api/health', { method: 'GET' })
  .then(function (r) { log('ДОШЁЛ: ' + r.status); document.title = 'REACHED'; })
  .catch(function (e) { log('ОШИБКА: ' + e.message); document.title = 'BLOCKED:' + e.message; });
</script></body></html>
"""


def main():
    temp = os.path.join(HERE, ".mixedtmp")
    os.makedirs(temp, exist_ok=True)
    cert = os.path.join(temp, "cert.pem")
    key = os.path.join(temp, "key.pem")
    if not (os.path.exists(cert) and os.path.exists(key)):
        print("Нужен сертификат. Создаём:")
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key,
             "-out", cert, "-days", "2", "-nodes", "-subj", "//CN=localhost"],
            check=True, capture_output=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"},
        )
    page = os.path.join(temp, "index.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(PAGE)

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=temp, **kw
    )
    httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert, keyfile=key)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    print(f"HTTPS-пробник: https://127.0.0.1:{port}/")
    print("Пробуем оттуда fetch на http://127.0.0.1:8766 …\n")

    chrome = None
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if os.path.exists(candidate):
            chrome = candidate
            break
    if not chrome:
        print("Chrome/Edge не найдены")
        return 0

    proc = subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--ignore-certificate-errors",
         "--virtual-time-budget=8000", "--dump-dom", f"https://127.0.0.1:{port}/"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    text = proc.stdout
    if "BLOCKED" in text:
        print("ВОСПРОИЗВЕЛО: браузер заблокировал запрос.")
        print("  https-страница -> http-сервер = mixed content, fetch падает: Failed to fetch")
    elif "REACHED" in text:
        print("Запрос ДОШЁЛ до сервера — mixed content не воспроизводится")
    else:
        print("Не удалось определить результат")
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

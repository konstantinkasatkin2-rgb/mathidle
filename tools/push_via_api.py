"""Кладёт коммит на GitHub через API, когда `git push` падает.

    python tools/push_via_api.py

Берёт текущий HEAD, создаёт недостающие блобы, дерево, коммит и двигает
ветку. Нужен потому, что git push на этой машине иногда отбивается
«Internal Server Error» — ошибка на стороне GitHub, а не у нас.
"""

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "konstantinkasatkin2-rgb/mathidle"
BRANCH = "master"
API = "https://api.github.com"


def gh(*args, binary=False):
    """Запускает gh/git и возвращает stdout."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True,
        encoding=None if binary else "utf-8", errors="replace",
    )
    if proc.returncode != 0:
        sys.exit("команда gh %s не сработала: %s"
                 % (" ".join(args), (proc.stderr or "").strip()[:300]))
    return proc.stdout if binary else proc.stdout


def git(*args) -> str:
    """Запускает git и возвращает stdout."""
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.exit("команда git %s не сработала: %s"
                 % (" ".join(args), (proc.stderr or "").strip()[:300]))
    return proc.stdout.strip()


def token() -> str:
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def api(method: str, path: str, body=None):
    """Запрос к API GitHub с авторизацией."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{API}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token()}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        sys.exit("API ответил %s: %s" % (err.code, err.read().decode()[:400]))


def main() -> int:
    head = git("rev-parse", "HEAD")
    message = git("log", "-1", "--pretty=%B")
    parent = git("rev-parse", f"origin/{BRANCH}")

    remote_head = gh("api", f"repos/{REPO}/commits/{BRANCH}",
                     "--jq", ".sha").strip()
    if remote_head == head:
        print("коммит уже на GitHub")
        return 0

    # Файлы коммита
    names = git("show", "--name-only", "--pretty=", head).split()
    if not names:
        sys.exit("в коммите нет файлов")
    print("файлов в коммите: %d" % len(names))

    base_tree = gh("api", f"repos/{REPO}/git/commits/{parent}",
                   "--jq", ".tree.sha").strip()
    entries = []
    for name in names:
        with open(name, "rb") as fh:
            raw = fh.read()
        blob = api("POST", f"/repos/{REPO}/git/blobs", {
            "content": base64.b64encode(raw).decode(),
            "encoding": "base64",
        })
        entries.append({
            "path": name,
            "mode": "100755" if os.access(name, os.X_OK) else "100644",
            "type": "blob",
            "sha": blob["sha"],
        })
        print("  залит %s" % name)

    tree = api("POST", f"/repos/{REPO}/git/trees", {
        "base_tree": base_tree, "tree": entries,
    })
    commit = api("POST", f"/repos/{REPO}/git/commits", {
        "message": message, "tree": tree["sha"], "parents": [parent],
    })
    api("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", {
        "sha": commit["sha"], "force": False,
    })

    print()
    print("залито: %s" % commit["sha"])
    print("ветка %s обновлена на %s" % (BRANCH, commit["sha"][:7]))

    # Локальная ветка должна узнать, что push состоялся
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{BRANCH}", commit["sha"]],
                   check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""Reset the IDE workspace to the imperfect 'hero' demo app (folder `demo/`).

Writes through the same REST API the IDE uses. Usage: uv run python demo/seed_workspace.py
Env: IDE_BACKEND_URL (default http://localhost:3001/api)
"""
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("IDE_BACKEND_URL", "http://localhost:3001/api").rstrip("/")
HERO = pathlib.Path(__file__).resolve().parent / "hero"
TARGET = "demo"


def call(method, path, body=None, query=None):
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, {"Content-Type": "application/json"}, method=method)
    try:
        return urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code


print("remove old demo folder:", call("DELETE", "/delete", query={"path": TARGET}))
for f in sorted(HERO.rglob("*")):
    if f.is_file():
        print(f"write {TARGET}/{f.relative_to(HERO)}:", call("POST", "/file", {"path": f"{TARGET}/{f.relative_to(HERO)}", "content": f.read_text()}))

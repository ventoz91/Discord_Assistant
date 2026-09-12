"""Deployed template-instance metadata: data/deployed_servers.json.

Each entry is a game server the web panel deployed from a template (Phase 3),
as opposed to the fixed servers wired up in gamefunc/ and configured via .env.
Tracks enough to reconstruct a gamefunc.compose_server.DockerComposeGameServer
for start/stop/status and to clean up fully on delete.
"""

import json
import os
import time

_STORE_PATH = os.path.join("data", "deployed_servers.json")

NAME_RE_SOURCE = r"^[a-z][a-z0-9-]{1,30}$"


def _load() -> list[dict]:
    if not os.path.exists(_STORE_PATH):
        return []
    with open(_STORE_PATH) as f:
        return json.load(f)


def _save(entries: list[dict]):
    os.makedirs("data", exist_ok=True)
    with open(_STORE_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def list_instances() -> list[dict]:
    return sorted(_load(), key=lambda e: e["created_ts"])


def get_instance(name: str) -> dict | None:
    for e in _load():
        if e["name"] == name:
            return e
    return None


def add_instance(name: str, template: str, host: str, user: str, compose_dir: str,
                  ports: list[dict], image: str) -> dict:
    """ports: list of {"host_port": int, "container_port": int, "protocol": "tcp"|"udp"}"""
    entries = _load()
    if any(e["name"] == name for e in entries):
        raise ValueError(f"an instance named {name!r} already exists")
    entry = {
        "name": name,
        "template": template,
        "host": host,
        "user": user,
        "compose_dir": compose_dir,
        "ports": ports,
        "image": image,
        "created_ts": int(time.time()),
    }
    entries.append(entry)
    _save(entries)
    return entry


def remove_instance(name: str) -> dict | None:
    entries = _load()
    for i, e in enumerate(entries):
        if e["name"] == name:
            entries.pop(i)
            _save(entries)
            return e
    return None

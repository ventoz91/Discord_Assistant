"""Catalog of game server templates offered by the "Deploy new server" page.

Each curated template's image/volume-path defaults are a best-effort starting
point, not a verified guarantee — third-party game server images vary in their
exact conventions and drift over time. The deploy form exposes the data volume
path as an editable field for exactly this reason: check the image's own docs
on first deploy and adjust if persistence doesn't land where expected.

The "custom" template has no curated fields — the user supplies the image,
port mappings, and environment variables directly, for anything not listed here.
"""

import yaml

TEMPLATES = {
    "terraria": {
        "label": "Terraria",
        "description": "Dedicated Terraria server (ryshe/terraria, TShock-based).",
        "image": "ryshe/terraria:latest",
        "default_volume_path": "/root/.local/share/Terraria/Worlds",
        "default_ports": [
            {"container_port": 7777, "protocol": "tcp", "label": "Game port"},
        ],
        "fields": [
            {"key": "WORLD", "label": "World name", "default": "world", "required": True},
            {"key": "DIFFICULTY", "label": "Difficulty (0=Classic, 1=Expert, 2=Master, 3=Journey)",
             "default": "0", "required": False},
            {"key": "MAXPLAYERS", "label": "Max players", "default": "8", "required": False},
        ],
    },
    "valheim": {
        "label": "Valheim (Linux/Docker)",
        "description": (
            "Dedicated Valheim server (lloesche/valheim-server), deployed as a "
            "standalone Linux/Docker instance."
        ),
        "image": "lloesche/valheim-server:latest",
        "default_volume_path": "/config",
        "default_ports": [
            {"container_port": 2456, "protocol": "udp", "label": "Game port"},
        ],
        "fields": [
            {"key": "SERVER_NAME", "label": "Server name", "default": "MyValheimServer", "required": True},
            {"key": "WORLD_NAME", "label": "World name", "default": "Dedicated", "required": True},
            {"key": "SERVER_PASS", "label": "Server password", "default": "", "required": True},
        ],
    },
    "custom": {
        "label": "Custom image",
        "description": "Any docker image — for anything not curated above.",
        "image": None,
        "default_volume_path": "/data",
        "default_ports": [],
        "fields": [],
        "custom": True,
    },
}


def render_compose_yaml(name: str, image: str, ports: list[dict], env: dict,
                         volume_path: str) -> str:
    """ports: list of {"host_port": int, "container_port": int, "protocol": "tcp"|"udp"}"""
    service = {
        "image": image,
        "container_name": name,
        "restart": "unless-stopped",
        "ports": [f"{p['host_port']}:{p['container_port']}/{p['protocol']}" for p in ports],
        "volumes": [f"./data:{volume_path}"],
    }
    if env:
        service["environment"] = env
    compose = {"services": {name: service}}
    return yaml.safe_dump(compose, sort_keys=False)

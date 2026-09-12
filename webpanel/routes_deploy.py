"""Phase 3: deploy new game servers from templates, and manage what's been
deployed. Everything here targets a single configured host (DEPLOY_TARGET_HOST
— GameDocker in practice) over SSH, reusing the same DockerComposeGameServer
used by the fixed servers. Deployed instances live in their own directory under
DEPLOY_BASE_DIR, one docker-compose.yml per instance, kept separate from the
hand-maintained main compose file so a deploy can never collide with
Minecraft/Satisfactory/Palworld.
"""

import asyncio
import logging
import os
import re
import shlex

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from gamefunc.compose_server import DockerComposeGameServer
from webpanel import store
from webpanel.templates_catalog import TEMPLATES, render_compose_yaml

logger = logging.getLogger("bot.webpanel")

router = APIRouter()
templates = Jinja2Templates(directory="webpanel/templates")

_NAME_RE = re.compile(store.NAME_RE_SOURCE)
_PORT_LINE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*/\s*(tcp|udp)\s*$", re.IGNORECASE)
# Names that would collide with a service in the hand-maintained GameDocker compose file.
_RESERVED_NAMES = {"minecraft", "minecraft-creative", "satisfactory", "palworld", "mc-proxy", "beszel-agent"}


def _deploy_target() -> DockerComposeGameServer:
    """Represents the deploy host itself (for host-wide checks like a port
    scan) rather than any one instance's compose service."""
    return DockerComposeGameServer(
        host=lambda: os.getenv("DEPLOY_TARGET_HOST", ""),
        user=lambda: os.getenv("DEPLOY_TARGET_USER", ""),
        compose_dir=lambda: os.getenv("DEPLOY_BASE_DIR", "/home/data/gameservers/deployed"),
        service_name="",
    )


def _instance_compose(inst: dict) -> DockerComposeGameServer:
    return DockerComposeGameServer(
        host=inst["host"], user=inst.get("user", ""), compose_dir=inst["compose_dir"],
        service_name=inst["name"], container_name=inst["name"],
    )


async def _port_in_use(target: DockerComposeGameServer, port: int) -> bool:
    ok, out = await target.run("ss -tuln")
    return ok and re.search(rf"[:.]{port}\b", out) is not None


async def _notify_discord(request: Request, label: str, name: str, message: str):
    bot = getattr(request.app.state, "bot", None)
    channel_id = os.getenv("PANEL_EVENTS_CHANNEL_ID", "").strip()
    if not bot or not channel_id:
        return
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(f"🌐 **Web panel:** {label} `{name}` — {message}")
    except Exception:
        logger.debug("panel->discord notify failed", exc_info=True)


async def _deployed_status(inst: dict) -> dict:
    online = await _instance_compose(inst).is_running()
    ports_str = ", ".join(f"{p['host_port']}/{p['protocol']}" for p in inst["ports"])
    connect = f"{inst['host']}:{inst['ports'][0]['host_port']}" if inst["ports"] else ""
    return {
        "id": f"deployed:{inst['name']}", "label": inst["name"], "kind": "deployed",
        "online": online, "detail": f"{inst['image']} · ports {ports_str}",
        "connect": connect, "redeployable": True,
        "deletable": True, "base_url": f"/deployed/{inst['name']}",
    }


# ── Deploy flow ──────────────────────────────────────────────────────────────

@router.get("/deploy", response_class=HTMLResponse)
async def deploy_picker(request: Request):
    return templates.TemplateResponse(request, "deploy_picker.html", {"templates": TEMPLATES})


@router.get("/deploy/{template_key}", response_class=HTMLResponse)
async def deploy_form(request: Request, template_key: str):
    tmpl = TEMPLATES.get(template_key)
    if not tmpl:
        return HTMLResponse("unknown template", status_code=404)
    return templates.TemplateResponse(
        request, "deploy_form.html", {"key": template_key, "tmpl": tmpl, "form": None, "error": None},
    )


@router.post("/deploy/{template_key}", response_class=HTMLResponse)
async def deploy_submit(request: Request, template_key: str):
    tmpl = TEMPLATES.get(template_key)
    if not tmpl:
        return HTMLResponse("unknown template", status_code=404)

    form = await request.form()

    def fail(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "deploy_form.html",
            {"key": template_key, "tmpl": tmpl, "form": form, "error": msg}, status_code=400,
        )

    name = (form.get("name") or "").strip().lower()
    if not _NAME_RE.match(name):
        return fail("Instance name must start with a letter and contain only lowercase letters, digits, "
                    "and hyphens (2-31 chars).")
    if name in _RESERVED_NAMES or store.get_instance(name):
        return fail(f"An instance named '{name}' already exists (or is reserved) — pick a different name.")

    target_host = os.getenv("DEPLOY_TARGET_HOST", "")
    if not target_host:
        return fail("DEPLOY_TARGET_HOST isn't set in .env — point it at the game-hosting VM (e.g. GameDocker) first.")

    if tmpl.get("custom"):
        image = (form.get("image") or "").strip()
        if not image:
            return fail("Image is required.")
        ports = []
        for line in (form.get("ports") or "").splitlines():
            line = line.strip()
            if not line:
                continue
            m = _PORT_LINE_RE.match(line)
            if not m:
                return fail(f"Bad port line {line!r} — expected host:container/tcp or host:container/udp, one per line.")
            ports.append({"host_port": int(m.group(1)), "container_port": int(m.group(2)),
                          "protocol": m.group(3).lower()})
        env = {}
        for line in (form.get("env") or "").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    else:
        image = tmpl["image"]
        ports = []
        for i, p in enumerate(tmpl["default_ports"]):
            raw = (form.get(f"port_{i}") or "").strip()
            if not raw.isdigit():
                return fail(f"{p['label']} must be a port number.")
            ports.append({"host_port": int(raw), "container_port": p["container_port"], "protocol": p["protocol"]})
        env = {}
        for f in tmpl["fields"]:
            val = (form.get(f["key"]) or f["default"] or "").strip()
            if f["required"] and not val:
                return fail(f"{f['label']} is required.")
            env[f["key"]] = val

    if not ports:
        return fail("At least one port mapping is required.")

    volume_path = (form.get("volume_path") or tmpl["default_volume_path"] or "/data").strip()

    probe = _deploy_target()
    for p in ports:
        if await _port_in_use(probe, p["host_port"]):
            return fail(f"Port {p['host_port']} looks already in use on the deploy host — pick another.")

    compose_dir = f'{os.getenv("DEPLOY_BASE_DIR", "/home/data/gameservers/deployed")}/{name}'
    compose_yaml = render_compose_yaml(name, image, ports, env, volume_path)

    instance = DockerComposeGameServer(
        host=target_host, user=os.getenv("DEPLOY_TARGET_USER", ""),
        compose_dir=compose_dir, service_name=name, container_name=name,
    )
    if not await instance.write_file(f"{compose_dir}/docker-compose.yml", compose_yaml):
        return fail("Couldn't write the compose file to the deploy host — check SSH access to DEPLOY_TARGET_HOST.")
    if not await instance.start():
        return fail("Compose file written, but `docker compose up -d` failed — check the bot log to investigate "
                     "(the instance directory on the host was NOT cleaned up automatically).")

    store.add_instance(
        name=name, template=template_key, host=target_host,
        user=os.getenv("DEPLOY_TARGET_USER", ""), compose_dir=compose_dir, ports=ports, image=image,
    )
    asyncio.create_task(_notify_discord(request, "Deployed", name, f"new {tmpl['label']} instance"))
    return RedirectResponse("/", status_code=303)


# ── Deployed-instance management ─────────────────────────────────────────────

@router.get("/deployed/{name}/row", response_class=HTMLResponse)
async def deployed_row(request: Request, name: str):
    inst = store.get_instance(name)
    if not inst:
        return HTMLResponse("unknown instance", status_code=404)
    return templates.TemplateResponse(request, "_server_row.html", {"s": await _deployed_status(inst)})


async def _deployed_action(request: Request, name: str, verb: str) -> HTMLResponse:
    inst = store.get_instance(name)
    if not inst:
        return HTMLResponse("unknown instance", status_code=404)
    compose = _instance_compose(inst)
    if verb == "start":
        ok = await compose.start()
        message = "Start requested." if ok else "Failed to start — check SSH/Docker config."
    elif verb == "stop":
        ok = await compose.stop()
        message = "Stop requested." if ok else "Failed to stop."
    else:
        ok = await compose.pull_and_redeploy()
        message = "Redeployed." if ok else "Redeploy failed."
    asyncio.create_task(_notify_discord(request, verb.capitalize(), name, message))
    status = await _deployed_status(inst)
    return templates.TemplateResponse(request, "_server_row.html", {"s": status, "message": message})


@router.post("/deployed/{name}/start", response_class=HTMLResponse)
async def deployed_start(request: Request, name: str):
    return await _deployed_action(request, name, "start")


@router.post("/deployed/{name}/stop", response_class=HTMLResponse)
async def deployed_stop(request: Request, name: str):
    return await _deployed_action(request, name, "stop")


@router.post("/deployed/{name}/redeploy", response_class=HTMLResponse)
async def deployed_redeploy(request: Request, name: str):
    return await _deployed_action(request, name, "redeploy")


@router.get("/deployed/{name}/delete", response_class=HTMLResponse)
async def deployed_delete_confirm(request: Request, name: str):
    inst = store.get_instance(name)
    if not inst:
        return HTMLResponse("unknown instance", status_code=404)
    return templates.TemplateResponse(request, "deploy_delete.html", {"name": name, "error": None})


@router.post("/deployed/{name}/delete", response_class=HTMLResponse)
async def deployed_delete_submit(request: Request, name: str, confirm_name: str = Form(...)):
    inst = store.get_instance(name)
    if not inst:
        return HTMLResponse("unknown instance", status_code=404)
    if confirm_name.strip() != name:
        return templates.TemplateResponse(
            request, "deploy_delete.html",
            {"name": name, "error": "Typed name didn't match — nothing was deleted."}, status_code=400,
        )
    compose = _instance_compose(inst)
    await compose.down()
    await compose.run(f"rm -rf {shlex.quote(inst['compose_dir'])}")
    store.remove_instance(name)
    asyncio.create_task(_notify_discord(request, "Deleted", name, "instance removed"))
    return RedirectResponse("/", status_code=303)

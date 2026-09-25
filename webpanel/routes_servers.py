"""Dashboard for the fixed servers the bot already manages (configured via
.env), plus Palworld. Wraps the same gamefunc/ classes cogs/servers.py uses —
no control logic is duplicated here.
"""

import asyncio
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from gamefunc.emucoach import EmucoachServer
from gamefunc.minecraft import MinecraftServer
from gamefunc.palworld import PalworldServer
from gamefunc.satisfactory import SatisfactoryServer
from gamefunc.valheim import EnshroudedServer, ValheimServer
from webpanel import store
from webpanel.routes_deploy import _deployed_status

logger = logging.getLogger("bot.webpanel")

router = APIRouter()
templates = Jinja2Templates(directory="webpanel/templates")

# Satisfactory/Palworld/Emucoach/Valheim/Enshrouded read their SSH/RCON config
# lazily on every call (see gamefunc/compose_server.py and each class), so a
# single process-lifetime instance is safe here and avoids e.g. Satisfactory
# re-fetching an auth token on every request.
_sf = SatisfactoryServer()
_pw = PalworldServer()
_valheim = ValheimServer()
_enshrouded = EnshroudedServer()
_emucoach = EmucoachServer()

# MinecraftServer reads its RCON/SSH settings once in __init__ (unlike the
# others above), so — matching how the Discord panels already build a fresh
# MinecraftServer() per command invocation — a new instance is constructed per
# request instead of cached, so .env changes take effect without a restart.

FIXED_SERVERS = [
    {"id": "minecraft_vanilla",  "label": "Minecraft — Vanilla",  "kind": "minecraft", "mc_type": "vanilla"},
    {"id": "minecraft_creative", "label": "Minecraft — Creative", "kind": "minecraft", "mc_type": "creative"},
    {"id": "satisfactory",       "label": "Satisfactory",         "kind": "satisfactory"},
    {"id": "palworld",           "label": "Palworld",             "kind": "palworld"},
    {"id": "valheim",            "label": "Valheim",               "kind": "valheim"},
    {"id": "enshrouded",         "label": "Enshrouded",            "kind": "enshrouded"},
    {"id": "emucoach",           "label": "EmuCoach (WoW)",        "kind": "emucoach"},
]

_WINDOWS_ONLY_NOTE = "Not available from this host — Windows-only control path (see README Known Limitations)."

# Reuses the same channels the bot's own event watchers already announce to,
# so a panel-driven action shows up exactly like a bot-driven one. Servers
# without a dedicated *_EVENTS_CHANNEL_ID fall back to the generic one.
_EVENTS_CHANNEL_ENV = {
    "minecraft_vanilla":  "MINECRAFT_EVENTS_CHANNEL_ID",
    "minecraft_creative": "MINECRAFT_CREATIVE_EVENTS_CHANNEL_ID",
    "satisfactory":       "SATISFACTORY_EVENTS_CHANNEL_ID",
}


def _find(server_id: str) -> dict | None:
    return next((s for s in FIXED_SERVERS if s["id"] == server_id), None)


async def _notify_discord(request: Request, entry: dict, action_label: str, message: str):
    """Best-effort: post the panel action to the same channel the server's own
    event watcher announces to. The panel runs in the same process as the bot
    (see main.py), so bot.get_channel/.send work directly — no webhook needed."""
    bot = getattr(request.app.state, "bot", None)
    channel_id = os.getenv(_EVENTS_CHANNEL_ENV.get(entry["id"], ""), "").strip() \
        or os.getenv("PANEL_EVENTS_CHANNEL_ID", "").strip()
    if not bot or not channel_id:
        return
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(f"🌐 **Web panel:** {action_label} `{entry['label']}` — {message}")
    except Exception:
        logger.debug("panel->discord notify failed", exc_info=True)


async def _status(entry: dict) -> dict:
    kind = entry["kind"]
    out = {
        **entry, "online": None, "detail": "", "connect": "", "redeployable": False,
        "deletable": False, "base_url": f"/servers/{entry['id']}",
    }
    try:
        if kind == "minecraft":
            mc = MinecraftServer()
            data, proxy_up = await asyncio.gather(
                mc.get_status(entry["mc_type"]), mc.proxy_running(entry["mc_type"]),
            )
            out["online"] = data is not None
            parts = []
            if data:
                tps = f" · {data['tps']} TPS" if data["tps"] is not None else ""
                parts.append(f"{data['current']}/{data['maximum']} players{tps}")
            if proxy_up is not None:
                parts.append("Proxy 🟢 online" if proxy_up else "Proxy 🔴 offline")
            out["detail"] = " · ".join(parts)
            out["connect"] = os.getenv(f"MINECRAFT_{entry['mc_type'].upper()}_CONNECT_URL", "")
            out["redeployable"] = True
        elif kind == "satisfactory":
            gs = await _sf.get_state()
            out["online"] = gs is not None
            if gs:
                out["detail"] = (f"{gs['num_players']}/{gs['player_limit']} players · Tier {gs['tech_tier']}"
                                  if gs["is_game_running"] else "No save loaded")
            out["connect"] = os.getenv("SATISFACTORY_CONNECT_URL", "")
            out["redeployable"] = True
        elif kind == "palworld":
            out["online"] = await _pw.is_running()
            out["connect"] = os.getenv("PALWORLD_CONNECT_URL", "")
            out["redeployable"] = True
        elif kind == "valheim":
            detail = await asyncio.to_thread(_valheim.server_status)
            out["detail"] = detail
            out["online"] = "running" in detail.lower()
        elif kind == "enshrouded":
            out["detail"] = "Status not tracked for Enshrouded — use Start/Stop directly."
        elif kind == "emucoach":
            detail = await _emucoach.server_status()
            out["detail"] = detail
            out["online"] = "🟢" in detail
            out["connect"] = os.getenv("EMUCOACH_CONNECT_URL", "")
    except AttributeError:
        # Valheim/Enshrouded call Windows-only subprocess APIs (CREATE_NEW_CONSOLE)
        # and can never succeed while the bot runs in its Linux container.
        out["detail"] = _WINDOWS_ONLY_NOTE
    except Exception as e:
        logger.warning("status check failed for %s: %s", entry["id"], e)
        out["detail"] = f"Error checking status: {e}"
    return out


async def _start(entry: dict) -> str:
    kind = entry["kind"]
    try:
        if kind == "minecraft":
            ok = await MinecraftServer().start(entry["mc_type"])
            return "Start requested." if ok else "Failed to start — check SSH/Docker config."
        if kind == "satisfactory":
            ok = await _sf.start()
            return "Start requested." if ok else "Failed to start — check SSH/Docker config."
        if kind == "palworld":
            ok = await _pw.start()
            return "Start requested." if ok else "Failed to start — check SSH/Docker config."
        if kind == "valheim":
            return await asyncio.to_thread(_valheim.start_server)
        if kind == "enshrouded":
            return await asyncio.to_thread(_enshrouded.start_server)
        if kind == "emucoach":
            return await _emucoach.start_server()
    except AttributeError:
        return _WINDOWS_ONLY_NOTE
    return "Unsupported action."


async def _stop(entry: dict) -> str:
    kind = entry["kind"]
    try:
        if kind == "minecraft":
            await MinecraftServer().stop(entry["mc_type"])
            return "Stop requested."
        if kind == "satisfactory":
            await _sf.stop()
            return "Stop requested."
        if kind == "palworld":
            await _pw.stop()
            return "Stop requested."
        if kind == "valheim":
            return await asyncio.to_thread(_valheim.stop_server)
        if kind == "enshrouded":
            return await asyncio.to_thread(_enshrouded.stop_server, "enshrouded_server.exe")
        if kind == "emucoach":
            return await _emucoach.stop_server()
    except AttributeError:
        return _WINDOWS_ONLY_NOTE
    return "Unsupported action."


async def _redeploy(entry: dict) -> str:
    kind = entry["kind"]
    if kind == "minecraft":
        ok = await MinecraftServer().pull_and_redeploy(entry["mc_type"])
        return "Redeployed." if ok else "Redeploy failed — check SSH/Docker config."
    if kind == "satisfactory":
        ok = await _sf.pull_and_redeploy()
        return "Redeployed." if ok else "Redeploy failed — check SSH/Docker config."
    if kind == "palworld":
        ok = await _pw.pull_and_redeploy()
        return "Redeployed." if ok else "Redeploy failed — check SSH/Docker config."
    return "Redeploy isn't supported for this server."


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    fixed = await asyncio.gather(*(_status(s) for s in FIXED_SERVERS))
    deployed_instances = store.list_instances()
    deployed = await asyncio.gather(*(_deployed_status(i) for i in deployed_instances))
    return templates.TemplateResponse(request, "dashboard.html", {"servers": fixed, "deployed": deployed})


@router.get("/servers/{server_id}/row", response_class=HTMLResponse)
async def server_row(request: Request, server_id: str):
    """Returns just this server's row — used by htmx polling to refresh in place."""
    entry = _find(server_id)
    if not entry:
        return HTMLResponse("unknown server", status_code=404)
    status = await _status(entry)
    return templates.TemplateResponse(request, "_server_row.html", {"s": status})


async def _do_action(request: Request, server_id: str, action, label: str) -> HTMLResponse:
    entry = _find(server_id)
    if not entry:
        return HTMLResponse("unknown server", status_code=404)
    message = await action(entry)
    asyncio.create_task(_notify_discord(request, entry, label, message))
    status = await _status(entry)
    return templates.TemplateResponse(request, "_server_row.html", {"s": status, "message": message})


@router.post("/servers/{server_id}/start", response_class=HTMLResponse)
async def start_server(request: Request, server_id: str):
    return await _do_action(request, server_id, _start, "Start")


@router.post("/servers/{server_id}/stop", response_class=HTMLResponse)
async def stop_server(request: Request, server_id: str):
    return await _do_action(request, server_id, _stop, "Stop")


@router.post("/servers/{server_id}/redeploy", response_class=HTMLResponse)
async def redeploy_server(request: Request, server_id: str):
    return await _do_action(request, server_id, _redeploy, "Redeploy")

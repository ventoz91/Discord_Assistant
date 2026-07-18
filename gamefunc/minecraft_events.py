import asyncio
import logging
import os
import re

from gamefunc.minecraft import _rcon_command, RCON_CONNECT_TIMEOUT

logger = logging.getLogger("bot.minecraft_events")

_POLL_INTERVAL = 300  # seconds between checks while the server is offline or the watcher is disabled


def _watcher_enabled() -> bool:
    return os.getenv('MINECRAFT_EVENTS_ENABLED', 'true').strip().lower() != 'false'

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_INFO_RE  = re.compile(r'(?:INFO\]:|INFO\]: )(.+)')

_CHAT_RE = re.compile(r'<(\w+)>\s(.+)')

# Tried most → least specific; first match wins.
# Each entry: (pattern, has_y).  Groups are always (x, y, z) or (x, z).
_COORD_PATTERNS = [
    (re.compile(r'(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)'), True),   # x, y, z
    (re.compile(r'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)'),   True),   # x y z
    (re.compile(r'(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)'),                       False),  # x, z
    (re.compile(r'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)'),                        False),  # x z
]

_DEATH_KEYWORDS = (
    'was slain', 'was shot', 'was fireballed', 'was killed', 'was pummeled',
    'fell from', 'fell off', 'fell out of', 'fell into',
    'drowned', 'burned to death', 'went up in flames', 'blew up',
    'hit the ground', ' died', 'suffocated',
    'was squished', 'was pricked', 'starved to death', 'withered away',
    'experienced kinetic energy', 'froze to death', 'was struck by lightning',
)


def _find_coords(line: str) -> tuple[str, str, str | None, str, str] | None:
    """Return (player, x, y_or_None, z, full_msg) if a chat line contains coords."""
    clean = _ANSI_RE.sub('', line)
    m_info = _INFO_RE.search(clean)
    if not m_info:
        return None
    m_chat = _CHAT_RE.match(m_info.group(1).strip())
    if not m_chat:
        return None
    player, text = m_chat.group(1), m_chat.group(2)
    for pattern, has_y in _COORD_PATTERNS:
        m = pattern.search(text)
        if m:
            if has_y:
                return (player, m.group(1), m.group(2), m.group(3), text)
            else:
                return (player, m.group(1), None, m.group(2), text)
    return None


def _classify(line: str) -> str | None:
    """Return a death event string, or None if the line is uninteresting."""
    clean = _ANSI_RE.sub('', line)
    for kw in _DEATH_KEYWORDS:
        if kw in clean:
            m = _INFO_RE.search(clean)
            return m.group(1).strip() if m else clean.strip()
    return None


class MinecraftEventWatcher:
    def __init__(self, server_key: str = 'VANILLA'):
        self._server_key = server_key.upper()
        self._task: asyncio.Task | None = None

    def start(self, bot, channel_id: int):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._watch_loop(bot, channel_id))

    def stop(self):
        if self._task:
            self._task.cancel()

    async def _watch_loop(self, bot, channel_id: int):
        key = self._server_key
        ssh_host = os.getenv(f'MINECRAFT_{key}_SSH_HOST', '')
        if not ssh_host:
            logger.info("MINECRAFT_%s_SSH_HOST not set — %s event watcher disabled", key, key.lower())
            return
        ssh_user = os.getenv(f'MINECRAFT_{key}_SSH_USER', '')
        target = f'{ssh_user}@{ssh_host}' if ssh_user else ssh_host
        container = os.getenv(f'MINECRAFT_{key}_CONTAINER', 'minecraft')

        while True:
            try:
                if not _watcher_enabled() or not await self._container_running(target, container):
                    await asyncio.sleep(_POLL_INTERVAL)
                    continue
                await self._stream(bot, channel_id, target, container)
                logger.info("Minecraft %s log stream ended — rechecking in %ds", key, _POLL_INTERVAL)
                await asyncio.sleep(_POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Minecraft %s event watcher error: %s: %s — retrying in %ds", key, type(e).__name__, e, _POLL_INTERVAL)
                await asyncio.sleep(_POLL_INTERVAL)

    async def _container_running(self, target: str, container: str) -> bool:
        """Cheap SSH check whether the Docker container is up. Fails silently to False."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                target, f"docker inspect -f '{{{{.State.Running}}}}' {container}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            return out.decode('utf-8', errors='replace').strip() == 'true'
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return False
        except Exception:
            return False

    async def _stream(self, bot, channel_id: int, target: str, container: str):
        proc = await asyncio.create_subprocess_exec(
            'ssh', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=30',
            target, f'docker logs --tail=0 -f {container}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Minecraft %s event watcher connected", self._server_key)
        try:
            async for raw in proc.stdout:
                line = raw.decode('utf-8', errors='replace').strip()
                event = _classify(line)
                if event:
                    asyncio.create_task(self._announce_death(bot, channel_id, event))
                coords = _find_coords(line)
                if coords:
                    asyncio.create_task(self._announce_coords(bot, channel_id, *coords))
        finally:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            stderr_out = await proc.stderr.read()
            await proc.wait()
            if stderr_out:
                logger.warning("Minecraft %s event watcher SSH stderr: %s", self._server_key, stderr_out.decode('utf-8', errors='replace').strip())

    async def _announce_coords(self, bot, channel_id: int, player: str, x: str, y: str | None, z: str, text: str):
        channel = bot.get_channel(channel_id)
        if not channel:
            return
        def fmt(v: str) -> str:
            f = float(v)
            return str(int(f)) if f == int(f) else v
        if y is not None:
            coords_str = f"X: {fmt(x)}, Y: {fmt(y)}, Z: {fmt(z)}"
        else:
            coords_str = f"X: {fmt(x)}, Z: {fmt(z)}"
        await channel.send(f"📍 **{player}** shared coordinates\n> {text}\n`{coords_str}`")

    async def _announce_death(self, bot, channel_id: int, event: str):
        channel = bot.get_channel(channel_id)
        if not channel:
            return

        # Extract player name — first word of every Minecraft death message
        m = re.match(r'(\w+)\s', event)
        player = m.group(1) if m else None

        coords_str = ''
        if player:
            key = self._server_key
            rcon_host = os.getenv(f'MINECRAFT_{key}_RCON_HOST', 'localhost')
            rcon_port = int(os.getenv(f'MINECRAFT_{key}_RCON_PORT', '25575'))
            rcon_pass = os.getenv(f'MINECRAFT_{key}_RCON_PASSWORD', '')
            try:
                raw = await asyncio.to_thread(
                    _rcon_command, rcon_host, rcon_port, rcon_pass,
                    f'data get entity {player} Pos', RCON_CONNECT_TIMEOUT,
                )
                nums = re.findall(r'-?\d+(?:\.\d+)?', raw)
                if len(nums) >= 3:
                    x, y, z = int(float(nums[0])), int(float(nums[1])), int(float(nums[2]))
                    coords_str = f'\n`X: {x}, Y: {y}, Z: {z}`'
            except Exception as e:
                logger.warning("Minecraft %s RCON coord lookup for %s failed: %s", key, player, e)

        await channel.send(f"💀 {event}{coords_str}")

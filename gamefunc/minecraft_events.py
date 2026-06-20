import asyncio
import logging
import os
import re

from openai import AsyncOpenAI

logger = logging.getLogger("bot.minecraft_events")

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

_SYSTEM = (
    "You are {personality}. "
    "A Minecraft server event just occurred. React in one short sentence in character — "
    "no @mentions, no quotation marks, no asterisks for emphasis."
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
    """Return a human-readable event string, or None if the line is uninteresting."""
    clean = _ANSI_RE.sub('', line)
    if 'joined the game' in clean:
        m = re.search(r'(\S+) joined the game', clean)
        return m.group(0) if m else 'Someone joined the game'
    if 'left the game' in clean:
        m = re.search(r'(\S+) left the game', clean)
        return m.group(0) if m else 'Someone left the game'
    for kw in _DEATH_KEYWORDS:
        if kw in clean:
            m = _INFO_RE.search(clean)
            return m.group(1).strip() if m else clean.strip()
    return None


class MinecraftEventWatcher:
    def __init__(self, openai_api_key: str):
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._task: asyncio.Task | None = None

    def start(self, bot, channel_id: int):
        self._task = asyncio.create_task(self._watch_loop(bot, channel_id))

    def stop(self):
        if self._task:
            self._task.cancel()

    async def _watch_loop(self, bot, channel_id: int):
        ssh_host = os.getenv('MINECRAFT_VANILLA_SSH_HOST', '')
        if not ssh_host:
            logger.info("MINECRAFT_VANILLA_SSH_HOST not set — Minecraft event watcher disabled")
            return
        ssh_user = os.getenv('MINECRAFT_VANILLA_SSH_USER', '')
        target = f'{ssh_user}@{ssh_host}' if ssh_user else ssh_host
        container = os.getenv('MINECRAFT_VANILLA_CONTAINER', 'minecraft')

        while True:
            try:
                await self._stream(bot, channel_id, target, container)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Minecraft event watcher crashed: %s: %s — retrying in 30s", type(e).__name__, e)
                await asyncio.sleep(30)

    async def _stream(self, bot, channel_id: int, target: str, container: str):
        proc = await asyncio.create_subprocess_exec(
            'ssh', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=30',
            target, f'docker logs --tail=0 -f {container}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Minecraft event watcher connected")
        try:
            async for raw in proc.stdout:
                line = raw.decode('utf-8', errors='replace').strip()
                event = _classify(line)
                if event:
                    asyncio.create_task(self._announce(bot, channel_id, event))
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
                logger.warning("Minecraft event watcher SSH stderr: %s", stderr_out.decode('utf-8', errors='replace').strip())

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

    async def _announce(self, bot, channel_id: int, event: str):
        channel = bot.get_channel(channel_id)
        if not channel:
            return
        personality = getattr(bot, 'chatgpt_behaviour', '')
        try:
            resp = await self._client.chat.completions.create(
                model=os.getenv('MODEL_CHAT', 'gpt-4o'),
                messages=[
                    {"role": "system", "content": _SYSTEM.format(personality=personality)},
                    {"role": "user",   "content": event},
                ],
                max_completion_tokens=60,
                temperature=1.2,
            )
            await channel.send(resp.choices[0].message.content.strip())
        except Exception as e:
            logger.warning("Event commentary failed: %s", e)

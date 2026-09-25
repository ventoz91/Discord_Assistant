import asyncio
import logging
import os
import re
import socket
import struct
import time

from gamefunc.compose_server import DockerComposeGameServer
from gamefunc.user_service import RemoteUserService

_COLOR_RE = re.compile(r'§.')

RCON_CONNECT_TIMEOUT = 5.0  # seconds per RCON request (socket-level, thread-safe)

logger = logging.getLogger("bot.minecraft")
_background: set[asyncio.Task] = set()  # keeps fire-and-forget tasks from being GC'd


class RconError(Exception):
    pass


def _rcon_command(host: str, port: int, password: str, command: str, timeout: float) -> str:
    """Minimal synchronous RCON client. Uses socket.settimeout(), no signals,
    so it is safe to run from a worker thread (unlike the mcrcon library which
    uses signal.alarm() and crashes outside the main thread).
    """
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)

        def send(req_id: int, req_type: int, payload: str):
            body = struct.pack('<ii', req_id, req_type) + payload.encode('utf-8') + b'\x00\x00'
            sock.sendall(struct.pack('<i', len(body)) + body)

        def recv_exact(n: int) -> bytes:
            buf = b''
            while len(buf) < n:
                chunk = sock.recv(n - len(buf))
                if not chunk:
                    raise RconError('connection closed')
                buf += chunk
            return buf

        def recv_packet():
            (length,) = struct.unpack('<i', recv_exact(4))
            data = recv_exact(length)
            resp_id, resp_type = struct.unpack('<ii', data[:8])
            return resp_id, resp_type, data[8:-2].decode('utf-8', errors='replace')

        # Login
        send(1, 3, password)
        resp_id, _, _ = recv_packet()
        if resp_id == -1:
            raise RconError('authentication failed')

        # Command
        send(2, 2, command)
        _, _, body = recv_packet()
        return body


class MinecraftServer:
    # Server types managed over SSH+Docker. Maps type -> compose service name.
    # 'modded' instead runs as a systemd user service on a desktop PC (the
    # Docker host can't run it well) — see self._modded.
    _SSH_COMPOSE_SERVICE = {
        'vanilla':  'minecraft',
        'creative': 'minecraft-creative',
    }

    def __init__(self):
        self.rcon_settings = {
            'vanilla': {
                'host':     os.getenv('MINECRAFT_VANILLA_RCON_HOST', 'localhost'),
                'port':     int(os.getenv('MINECRAFT_VANILLA_RCON_PORT', 25575)),
                'password': os.getenv('MINECRAFT_VANILLA_RCON_PASSWORD', ''),
            },
            'modded': {
                'host':     os.getenv('MINECRAFT_MODDED_RCON_HOST', 'localhost'),
                'port':     int(os.getenv('MINECRAFT_MODDED_RCON_PORT', 25575)),
                'password': os.getenv('MINECRAFT_MODDED_RCON_PASSWORD', ''),
            },
            'creative': {
                'host':     os.getenv('MINECRAFT_CREATIVE_RCON_HOST', 'localhost'),
                'port':     int(os.getenv('MINECRAFT_CREATIVE_RCON_PORT', 25575)),
                'password': os.getenv('MINECRAFT_CREATIVE_RCON_PASSWORD', ''),
            },
        }
        # vanilla/creative are SSH+Docker-compose services; delegate that plumbing
        # to the shared DockerComposeGameServer instead of duplicating it (also
        # gives us pull_and_redeploy() for free).
        self._compose = {
            server_type: DockerComposeGameServer(
                host=self._env_getter(server_type, 'SSH_HOST'),
                user=self._env_getter(server_type, 'SSH_USER'),
                compose_dir=self._compose_dir_getter(server_type),
                service_name=service,
            )
            for server_type, service in self._SSH_COMPOSE_SERVICE.items()
        }
        self._modded = RemoteUserService(
            'MINECRAFT_MODDED_SSH_HOST', 'MINECRAFT_MODDED_SSH_USER',
            'MINECRAFT_MODDED_SERVICE', default_unit='minecraft-modded',
        )

    @staticmethod
    def _env_getter(server_type: str, suffix: str):
        key = f'MINECRAFT_{server_type.upper()}_{suffix}'
        return lambda: os.getenv(key, '')

    @staticmethod
    def _compose_dir_getter(server_type: str):
        key = f'MINECRAFT_{server_type.upper()}_COMPOSE_DIR'
        return lambda: os.getenv(key, os.getenv('MINECRAFT_VANILLA_COMPOSE_DIR', '/home/data'))

    def _proxy(self, server_type: str) -> DockerComposeGameServer | None:
        """The Velocity proxy in front of the Docker servers — the only thing
        publishing the player port (25565), so a backend started without it is
        up (RCON answers, panel says online) but unjoinable. Same host/compose
        dir as the backend. MINECRAFT_PROXY_SERVICE='' disables."""
        service = os.getenv('MINECRAFT_PROXY_SERVICE', 'mc-proxy').strip()
        if not service or server_type not in self._compose:
            return None
        return DockerComposeGameServer(
            host=self._env_getter(server_type, 'SSH_HOST'),
            user=self._env_getter(server_type, 'SSH_USER'),
            compose_dir=self._compose_dir_getter(server_type),
            service_name=service,
        )

    async def proxy_running(self, server_type: str = 'vanilla') -> bool | None:
        """Whether the proxy container is up; None if no proxy is configured.
        Needed alongside RCON status, which bypasses the proxy entirely."""
        proxy = self._proxy(server_type)
        return await proxy.is_running() if proxy else None

    async def start(self, server_type: str) -> bool:
        if server_type == 'modded':
            if not await self._modded.start():
                return False
            task = asyncio.create_task(self._reload_when_ready())
            _background.add(task)
            task.add_done_callback(_background.discard)
            return True
        if server_type not in self._compose:
            return False
        if not os.getenv(f'MINECRAFT_{server_type.upper()}_SSH_HOST', ''):
            return False
        if not await self._compose[server_type].start():
            return False
        # Bring the proxy up too. Its compose depends_on lists both backends
        # as required, so this also starts the other Minecraft server. Left
        # running on stop: it's harmless idle and the other backend may still
        # need it.
        proxy = self._proxy(server_type)
        return await proxy.start() if proxy else True

    async def pull_and_redeploy(self, server_type: str) -> bool:
        """Only meaningful for the SSH+Docker types (vanilla/creative)."""
        compose = self._compose.get(server_type)
        return await compose.pull_and_redeploy() if compose else False

    async def _rcon(self, server_type: str, command: str, timeout: float = RCON_CONNECT_TIMEOUT) -> str:
        info = self.rcon_settings[server_type]
        return await asyncio.to_thread(
            _rcon_command,
            info['host'], info['port'], info['password'], command, timeout,
        )

    async def _reload_when_ready(self):
        """The modded server's datapack functions (Legendary Encounters spawns
        and dungeons, Swapballs, ...) fail to parse at startup — LuckPerms
        isn't initialised yet when they're permission-checked (NPE in
        VerboseHandler; 33 functions, verified 2026-09-25). A `reload` once the
        server is up parses them all cleanly. MINECRAFT_MODDED_RELOAD_ON_START
        =false disables."""
        if os.getenv('MINECRAFT_MODDED_RELOAD_ON_START', 'true').strip().lower() == 'false':
            return
        try:
            if await self.wait_until_ready('modded', timeout=300):
                await asyncio.sleep(5)  # let startup finish settling
                await self._rcon('modded', 'reload', timeout=120)  # slow on a big modpack
                logger.info("modded: post-start datapack reload done")
        except Exception:
            logger.warning("modded: post-start reload failed", exc_info=True)

    async def stop(self, server_type: str) -> str:
        try:
            result = await self._rcon(server_type, 'stop')
            if server_type == 'modded' and self._modded.configured():
                # RCON `stop` saves the world, but a mod thread keeps the JVM
                # alive afterwards (seen 2026-09-25: saved, RCON closed, process
                # still running and holding its heap). Once RCON is down the
                # save is done, so stopping the unit just reaps the process.
                await self.wait_until_stopped('modded', timeout=90)
                await self._modded.stop()
            return result
        except Exception as e:
            # RCON unreachable: for the PC-hosted modded server, stopping the
            # systemd unit still shuts it down cleanly (SIGTERM saves the world).
            if server_type == 'modded' and self._modded.configured():
                return 'Stopped via systemd.' if await self._modded.stop() else str(e)
            return str(e)

    async def players(self, server_type: str) -> str:
        try:
            return await self._rcon(server_type, 'list')
        except Exception as e:
            return str(e)

    async def get_status(self, server_type: str) -> dict | None:
        """Returns {current, maximum, names, tps} or None if offline."""
        try:
            list_resp = await self._rcon(server_type, 'list')
            m = re.search(r'(\d+) of a max of (\d+)', list_resp)
            if not m:
                return None
            current, maximum = int(m.group(1)), int(m.group(2))
            name_part = list_resp.split(':', 1)[-1].strip() if ':' in list_resp else ''
            names = [n.strip() for n in name_part.split(',') if n.strip()] if name_part else []

            tps = None
            try:
                tps_resp = _COLOR_RE.sub('', await self._rcon(server_type, 'spark tps')).replace('*', '')
                vals = [float(n) for n in re.findall(r'\d+\.\d+', tps_resp) if 0 < float(n) <= 21]
                tps = round(vals[0], 1) if vals else None
            except Exception:
                pass

            return {'current': current, 'maximum': maximum, 'names': names, 'tps': tps}
        except Exception:
            return None

    async def is_running(self, server_type: str) -> bool:
        try:
            await self._rcon(server_type, 'list')
            return True
        except Exception:
            return False

    async def wait_until_ready(self, server_type: str, timeout: int = 300) -> bool:
        print(f"[minecraft] waiting for {server_type} RCON (up to {timeout}s)...")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                await self._rcon(server_type, 'list')
                print(f"[minecraft] {server_type} RCON connected — server ready")
                return True
            except Exception as e:
                remaining = int(deadline - time.monotonic())
                print(f"[minecraft] {server_type} not ready yet ({e}), {remaining}s remaining")
                await asyncio.sleep(5)
        print(f"[minecraft] {server_type} timed out waiting for RCON")
        return False

    async def wait_until_stopped(self, server_type: str, timeout: int = 60) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self.is_running(server_type):
                return True
            await asyncio.sleep(3)
        return False

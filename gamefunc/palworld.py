import os

from gamefunc.compose_server import DockerComposeGameServer


class PalworldServer:
    """SSH+Docker control for the Palworld server on GameDocker. No stateless
    status API is configured today (see /home/data/gameservers/palworld/.env on
    the host, not checked by this code), so status is the container's actual
    running state via `docker inspect` rather than a player count — good enough
    to drive start/stop/redeploy from the panel. RCON-based player counts can be
    added later if RCON is ever enabled in that .env.
    """

    def __init__(self):
        self._compose = DockerComposeGameServer(
            host=lambda: os.getenv('PALWORLD_SSH_HOST', ''),
            user=lambda: os.getenv('PALWORLD_SSH_USER', ''),
            compose_dir=lambda: os.getenv('PALWORLD_COMPOSE_DIR', '/home/data'),
            service_name='palworld',
            container_name='palworld-server',
        )

    async def start(self) -> bool:
        return await self._compose.start()

    async def stop(self) -> bool:
        return await self._compose.stop()

    async def pull_and_redeploy(self) -> bool:
        return await self._compose.pull_and_redeploy()

    async def is_running(self) -> bool:
        return await self._compose.is_running()

    async def wait_until_ready(self, timeout: int = 120) -> bool:
        return await self._compose.wait_until_ready(timeout)

    async def wait_until_stopped(self, timeout: int = 60) -> bool:
        return await self._compose.wait_until_stopped(timeout)

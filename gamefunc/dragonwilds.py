import os

from gamefunc.compose_server import DockerComposeGameServer


class DragonwildsServer:
    """SSH+Docker control for the RuneScape: Dragonwilds server on GameDocker.
    Same shape as PalworldServer: no stateless status API is configured, so
    status is the container's actual running state via `docker inspect` rather
    than a player count.

    No pull_and_redeploy: the GameDocker compose service uses `build:` (a
    custom image, not a pulled one — see /home/data/gameservers/dragonwilds-build
    on the host), and the container's own entrypoint runs DepotDownloader to
    update the game on every start, so a plain restart already picks up
    updates. `docker compose pull` would be meaningless for a build-context
    service.
    """

    def __init__(self):
        self._compose = DockerComposeGameServer(
            host=lambda: os.getenv('DRAGONWILDS_SSH_HOST', ''),
            user=lambda: os.getenv('DRAGONWILDS_SSH_USER', ''),
            compose_dir=lambda: os.getenv('DRAGONWILDS_COMPOSE_DIR', '/home/data'),
            service_name='dragonwilds',
            container_name='dragonwilds',
        )

    async def start(self) -> bool:
        return await self._compose.start()

    async def stop(self) -> bool:
        return await self._compose.stop()

    async def is_running(self) -> bool:
        return await self._compose.is_running()

    async def wait_until_ready(self, timeout: int = 120) -> bool:
        return await self._compose.wait_until_ready(timeout)

    async def wait_until_stopped(self, timeout: int = 60) -> bool:
        return await self._compose.wait_until_stopped(timeout)

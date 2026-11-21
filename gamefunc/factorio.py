import os

from gamefunc.compose_server import DockerComposeGameServer


class FactorioServer:
    """SSH+Docker control for the Factorio (vanilla, no Space Age) server on
    GameDocker. Same shape as DragonwildsServer: status is the container's
    running state via `docker inspect`, not a player count.

    No pull_and_redeploy: the compose service pins an exact image tag
    (factoriotools/factorio:stable-X.Y.Z), so `docker compose pull` would be a
    no-op — version bumps are a deliberate tag edit on the host, so saves are
    never migrated to a new game version by surprise.

    The server's own settings keep it safe to leave unattended: auto_pause
    (game freezes with nobody connected), peaceful mode, enemy expansion off,
    time-based evolution 0 — see /home/data/gameservers/factorio/config.
    """

    def __init__(self):
        self._compose = DockerComposeGameServer(
            host=lambda: os.getenv('FACTORIO_SSH_HOST', ''),
            user=lambda: os.getenv('FACTORIO_SSH_USER', ''),
            compose_dir=lambda: os.getenv('FACTORIO_COMPOSE_DIR', '/home/data'),
            service_name='factorio',
            container_name='factorio',
        )

    async def start(self) -> bool:
        return await self._compose.start()

    async def stop(self) -> bool:
        return await self._compose.stop()

    async def is_running(self) -> bool:
        return await self._compose.is_running()

    async def wait_until_ready(self, timeout: int = 120) -> bool:
        return await self._compose.wait_until_ready(timeout)

    async def wait_until_stopped(self, timeout: int = 90) -> bool:
        return await self._compose.wait_until_stopped(timeout)

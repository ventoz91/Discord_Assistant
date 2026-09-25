import asyncio
import os


class RemoteUserService:
    """A systemd *user* service on another machine, controlled over SSH —
    used for game servers that run on a desktop PC rather than in Docker
    (e.g. modded Minecraft, which needs more hardware than the Docker host
    has). The host side is scoped by deploy/bot-ssh-gate-systemd.sh, which
    only allows `systemctl --user start|stop|is-active <unit>`.

    host/user/unit are env var names, read on every call so .env changes take
    effect without a restart (matching DockerComposeGameServer).
    """

    def __init__(self, host_env: str, user_env: str, unit_env: str, default_unit: str):
        self._host_env = host_env
        self._user_env = user_env
        self._unit_env = unit_env
        self._default_unit = default_unit

    def configured(self) -> bool:
        return bool(os.getenv(self._host_env, '').strip())

    def unit(self) -> str:
        return os.getenv(self._unit_env, '').strip() or self._default_unit

    def _target(self) -> str:
        host = os.getenv(self._host_env, '').strip()
        user = os.getenv(self._user_env, '').strip()
        return f'{user}@{host}' if user else host

    async def _systemctl(self, verb: str, timeout: float = 20) -> tuple[bool, str]:
        if not self.configured():
            return False, 'no SSH host configured'
        proc = await asyncio.create_subprocess_exec(
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            self._target(), f'systemctl --user {verb} {self.unit()}',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False, 'timed out'
        text = (out or err).decode('utf-8', errors='replace').strip()
        return proc.returncode == 0, text

    async def start(self) -> bool:
        ok, _ = await self._systemctl('start')
        return ok

    async def stop(self) -> bool:
        ok, _ = await self._systemctl('stop', timeout=120)
        return ok

    async def is_active(self) -> bool:
        # is-active exits non-zero for inactive/failed, so read the text too.
        _, out = await self._systemctl('is-active')
        return out == 'active'

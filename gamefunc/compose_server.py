import asyncio
import os
import shlex
import subprocess
import time


class DockerComposeGameServer:
    """Shared control logic for a game server hosted as a docker-compose service on
    a remote host, controlled over SSH. Used directly by fixed servers (Satisfactory,
    Palworld) and by user-deployed template instances (webpanel/routes_deploy.py).

    host/user/compose_dir accept either a plain string (fixed value — used for
    deployed instances, whose settings live in the deployed-servers store, not
    .env) or a zero-arg callable (evaluated fresh on every call — used by the
    fixed servers so `.env` changes take effect without a bot restart, matching
    every other config value in this project).
    """

    def __init__(self, host, user, compose_dir, service_name: str, container_name: str | None = None):
        self._host = host
        self._user = user
        self._compose_dir = compose_dir
        self.service_name = service_name
        self.container_name = container_name or service_name

    @staticmethod
    def _resolve(value) -> str:
        return value() if callable(value) else value

    def ssh_target(self) -> str:
        host = self._resolve(self._host)
        user = self._resolve(self._user)
        return f'{user}@{host}' if user else host

    def compose_dir(self) -> str:
        return self._resolve(self._compose_dir)

    async def _ssh_run(self, remote_cmd: str, timeout: float = 30,
                        input_text: str | None = None) -> tuple[bool, str]:
        """Runs remote_cmd on the target host over SSH. Returns (ok, output)."""
        target = self.ssh_target()
        if not target:
            return False, 'no SSH host configured'
        cmd = ['ssh', '-o', 'BatchMode=yes', target, remote_cmd]
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, timeout=timeout, capture_output=True, text=True,
                input=input_text,
            )
            if result.returncode != 0:
                return False, (result.stderr or result.stdout).strip()
            return True, result.stdout.strip()
        except Exception as e:
            return False, str(e)

    async def run(self, remote_cmd: str, timeout: float = 15) -> tuple[bool, str]:
        """Runs an arbitrary command on the target host — e.g. a port-collision
        check (`ss -tuln`) before deploying a new instance. Public wrapper around
        _ssh_run for callers that aren't doing a compose subcommand."""
        return await self._ssh_run(remote_cmd, timeout=timeout)

    async def write_file(self, remote_path: str, content: str, timeout: float = 15) -> bool:
        """Writes content to remote_path on the target host, creating parent
        directories as needed. Used to lay down a generated docker-compose.yml
        for a newly deployed template instance."""
        d = shlex.quote(os.path.dirname(remote_path))
        p = shlex.quote(remote_path)
        ok, _ = await self._ssh_run(f'mkdir -p {d} && cat > {p}', timeout=timeout, input_text=content)
        return ok

    async def _ssh_compose(self, subcmd: str, timeout: float = 30) -> tuple[bool, str]:
        d = shlex.quote(self.compose_dir())
        return await self._ssh_run(f'cd {d} && docker compose {subcmd}', timeout=timeout)

    async def start(self) -> bool:
        ok, _ = await self._ssh_compose(f'up -d {self.service_name}')
        return ok

    async def stop(self) -> bool:
        ok, _ = await self._ssh_compose(f'stop {self.service_name}')
        return ok

    async def pull_and_redeploy(self) -> bool:
        """docker compose pull && up -d for this service. Brief downtime while the
        container recreates."""
        ok, _ = await self._ssh_compose(f'pull {self.service_name}', timeout=120)
        if not ok:
            return False
        ok, _ = await self._ssh_compose(f'up -d {self.service_name}', timeout=60)
        return ok

    async def down(self) -> bool:
        """Stops and removes the container (docker compose down). Used when
        deleting a deployed instance — does not touch other services in the
        same compose file."""
        ok, _ = await self._ssh_compose(f'down {self.service_name}', timeout=60)
        return ok

    async def is_running(self) -> bool:
        ok, out = await self._ssh_run(
            "docker inspect -f '{{.State.Running}}' " + shlex.quote(self.container_name),
            timeout=10,
        )
        return ok and out.strip() == 'true'

    async def wait_until_ready(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.is_running():
                return True
            await asyncio.sleep(3)
        return False

    async def wait_until_stopped(self, timeout: int = 60) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self.is_running():
                return True
            await asyncio.sleep(3)
        return False

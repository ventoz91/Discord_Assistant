import asyncio
import base64
import logging
import ntpath
import os

logger = logging.getLogger("bot.emucoach")

_SSH_TIMEOUT = 90  # seconds for a remote command round-trip (start waits on the DB)


class EmucoachServer:
    """Starts/stops the EmuCoach WoW repack on a Windows VM over SSH.

    Requires OpenSSH Server enabled on the VM with key auth. Processes are
    spawned via WMI (Win32_Process Create) so they detach from the SSH session
    and keep running after it closes. Start order: database → auth → world.
    """

    def _ssh_target(self) -> str:
        host = os.getenv('EMUCOACH_SSH_HOST', '')
        user = os.getenv('EMUCOACH_SSH_USER', '')
        return f'{user}@{host}' if user else host

    def _dir(self) -> str:
        return os.getenv('EMUCOACH_DIR', r'C:\GameServers\CATASILVER')

    def _db_start(self) -> str:
        return os.getenv('EMUCOACH_DB_START', r'Database\start_mysql.bat')

    def _auth_start(self) -> str:
        return os.getenv('EMUCOACH_AUTH_START', r'Repack\authserver.exe')

    def _world_start(self) -> str:
        return os.getenv('EMUCOACH_WORLD_START', r'Repack\worldserver.exe')

    def _proc_names(self) -> tuple[str, str, str]:
        """Process names (no extension) for db, auth, world."""
        auth = ntpath.splitext(ntpath.basename(self._auth_start()))[0]
        world = ntpath.splitext(ntpath.basename(self._world_start()))[0]
        return ('mysqld', auth, world)

    async def _run_ps(self, script: str) -> str | None:
        """Run a PowerShell script on the VM over SSH. Returns stdout, or None on failure."""
        target = self._ssh_target()
        if not target:
            return None
        encoded = base64.b64encode(script.encode('utf-16-le')).decode()
        proc = await asyncio.create_subprocess_exec(
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            target, f'powershell -NoProfile -EncodedCommand {encoded}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=_SSH_TIMEOUT)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            logger.warning("EmuCoach SSH command timed out")
            return None
        if proc.returncode != 0:
            logger.warning("EmuCoach SSH command failed (rc=%s): %s",
                           proc.returncode, err.decode('utf-8', errors='replace').strip())
            return None
        return out.decode('utf-8', errors='replace')

    async def _running_procs(self) -> set[str] | None:
        """Which of the repack processes are currently running. None if VM unreachable."""
        db, auth, world = self._proc_names()
        out = await self._run_ps(
            f"(Get-Process {db},{auth},{world} -ErrorAction SilentlyContinue "
            f"| Select-Object -ExpandProperty Name) -join ','"
        )
        if out is None:
            return None
        return {p.strip().lower() for p in out.strip().split(',') if p.strip()}

    def _launch_snippet(self, rel_path: str, proc_name: str, post_sleep: int = 0) -> str:
        """PowerShell that spawns rel_path detached via WMI, skipping if already running."""
        full = ntpath.join(self._dir(), rel_path)
        cwd = ntpath.dirname(full)
        if rel_path.lower().endswith(('.bat', '.cmd')):
            cmdline = f'cmd.exe /c "{full}"'
        else:
            cmdline = f'"{full}"'
        sleep = f'; Start-Sleep -Seconds {post_sleep}' if post_sleep else ''
        return (
            f"if (-not (Get-Process {proc_name} -ErrorAction SilentlyContinue)) {{ "
            f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
            f"@{{ CommandLine = '{cmdline}'; CurrentDirectory = '{cwd}' }} | Out-Null{sleep} }}"
        )

    def _connect_line(self) -> str:
        connect = os.getenv('EMUCOACH_CONNECT_URL', '')
        return f'\nConnect: `{connect}`' if connect else ''

    async def start_server(self) -> str:
        if not os.getenv('EMUCOACH_SSH_HOST', ''):
            return "⚙️ EmuCoach isn't configured — set EMUCOACH_SSH_HOST in .env."
        db, auth, world = self._proc_names()
        running = await self._running_procs()
        if running is None:
            return "❓ Can't reach the EmuCoach VM over SSH — is it powered on?"
        if {auth.lower(), world.lower()} <= running:
            return f"🟢 The WoW server is already online.{self._connect_line()}"

        db_wait = int(os.getenv('EMUCOACH_DB_WAIT', '10'))
        script = '; '.join([
            self._launch_snippet(self._db_start(), db, post_sleep=db_wait),
            self._launch_snippet(self._auth_start(), auth),
            self._launch_snippet(self._world_start(), world),
        ])
        if await self._run_ps(script) is None:
            return "❌ Couldn't start the WoW server — check the bot log for SSH errors."
        return ("🟢 Starting the WoW server — database, auth, and world are launching. "
                f"Give the world server a few minutes to load.{self._connect_line()}")

    async def stop_server(self) -> str:
        if not os.getenv('EMUCOACH_SSH_HOST', ''):
            return "⚙️ EmuCoach isn't configured — set EMUCOACH_SSH_HOST in .env."
        db, auth, world = self._proc_names()
        running = await self._running_procs()
        if running is None:
            return "❓ Can't reach the EmuCoach VM over SSH — is it powered on?"
        if not running:
            return "🔴 The WoW server is already stopped."
        script = (
            f"Stop-Process -Name {world},{auth} -Force -ErrorAction SilentlyContinue; "
            f"Start-Sleep -Seconds 2; "
            f"Stop-Process -Name {db} -Force -ErrorAction SilentlyContinue"
        )
        if await self._run_ps(script) is None:
            return "❌ Couldn't stop the WoW server — check the bot log for SSH errors."
        return "🔴 WoW server stopped (world, auth, and database)."

    async def server_status(self) -> str:
        if not os.getenv('EMUCOACH_SSH_HOST', ''):
            return "⚙️ EmuCoach isn't configured — set EMUCOACH_SSH_HOST in .env."
        db, auth, world = self._proc_names()
        running = await self._running_procs()
        if running is None:
            return "❓ Can't reach the EmuCoach VM over SSH — is it powered on?"
        if not running:
            return "🔴 Offline — nothing is running."
        parts = [
            f"Database: {'🟢' if db.lower() in running else '🔴'}",
            f"Auth: {'🟢' if auth.lower() in running else '🔴'}",
            f"World: {'🟢' if world.lower() in running else '🔴'}",
        ]
        if {db.lower(), auth.lower(), world.lower()} <= running:
            return f"🟢 Online — {' · '.join(parts)}{self._connect_line()}"
        return f"🟡 Partially running — {' · '.join(parts)}"

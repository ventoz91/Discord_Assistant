import subprocess
import asyncio
import os
import shlex
import time
from mcrcon import MCRcon

RCON_CONNECT_TIMEOUT = 3  # seconds per connection attempt


class MinecraftServer:
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
        }
        self.server_dirs = {
            'vanilla': os.getenv('MINECRAFT_VANILLA_DIR', ''),
            'modded':  os.getenv('MINECRAFT_MODDED_DIR', ''),
        }

    def start(self, server_type: str) -> bool:
        server_dir = self.server_dirs.get(server_type, '')
        if not server_dir:
            return False
        cmd = f'kitty --hold -d {server_dir} -e bash -c "./newrun.sh"'
        subprocess.Popen(shlex.split(cmd))
        return True

    async def _rcon(self, server_type: str, command: str) -> str:
        info = self.rcon_settings[server_type]
        def _run():
            with MCRcon(info['host'], info['password'], info['port'], timeout=RCON_CONNECT_TIMEOUT) as mcr:
                return mcr.command(command)
        return await asyncio.to_thread(_run)

    async def stop(self, server_type: str) -> str:
        try:
            return await self._rcon(server_type, 'stop')
        except Exception as e:
            return str(e)

    async def players(self, server_type: str) -> str:
        try:
            return await self._rcon(server_type, 'list')
        except Exception as e:
            return str(e)

    def is_running(self, server_type: str) -> bool:
        info = self.rcon_settings[server_type]
        try:
            with MCRcon(info['host'], info['password'], info['port'], timeout=RCON_CONNECT_TIMEOUT) as mcr:
                mcr.command('list')
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
            running = await asyncio.to_thread(self.is_running, server_type)
            if not running:
                return True
            await asyncio.sleep(3)
        return False

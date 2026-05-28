import subprocess
import asyncio
import os
import shlex
import socket
import struct
import time

RCON_CONNECT_TIMEOUT = 5.0  # seconds per RCON request (socket-level, thread-safe)


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
        return await asyncio.to_thread(
            _rcon_command,
            info['host'], info['port'], info['password'], command, RCON_CONNECT_TIMEOUT,
        )

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

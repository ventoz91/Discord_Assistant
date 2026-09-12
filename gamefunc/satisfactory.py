import asyncio
import os
import time

import aiohttp

from gamefunc.compose_server import DockerComposeGameServer

_API_TIMEOUT = aiohttp.ClientTimeout(total=5)


class SatisfactoryServer:
    def __init__(self):
        self._token: str | None = None
        self._compose = DockerComposeGameServer(
            host=lambda: os.getenv('SATISFACTORY_SSH_HOST', ''),
            user=lambda: os.getenv('SATISFACTORY_SSH_USER', ''),
            compose_dir=lambda: os.getenv('SATISFACTORY_COMPOSE_DIR', '/home/data'),
            service_name='satisfactory',
        )

    def _api_url(self) -> str:
        host = os.getenv('SATISFACTORY_API_HOST') or os.getenv('SATISFACTORY_SSH_HOST', '')
        port = os.getenv('SATISFACTORY_API_PORT', '7777')
        return f'https://{host}:{port}/api/v1'

    async def start(self) -> bool:
        return await self._compose.start()

    async def stop(self) -> bool:
        return await self._compose.stop()

    async def pull_and_redeploy(self) -> bool:
        return await self._compose.pull_and_redeploy()

    async def _call(self, session: aiohttp.ClientSession, fn: str,
                    data: dict | None = None, token: str | None = None) -> dict:
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        async with session.post(
            self._api_url(),
            json={'function': fn, 'data': data or {}},
            headers=headers,
            ssl=False,
            timeout=_API_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _refresh_token(self, session: aiohttp.ClientSession) -> str:
        r = await self._call(session, 'PasswordlessLogin',
                             {'minimumPrivilegeLevel': 'NotAuthenticated'})
        return r['data']['authenticationToken']

    async def get_state(self) -> dict | None:
        """Returns server game state dict, or None if unreachable."""
        try:
            async with aiohttp.ClientSession() as session:
                if not self._token:
                    self._token = await self._refresh_token(session)
                try:
                    r = await self._call(session, 'QueryServerState', token=self._token)
                except aiohttp.ClientResponseError as e:
                    if e.status == 401:
                        self._token = await self._refresh_token(session)
                        r = await self._call(session, 'QueryServerState', token=self._token)
                    else:
                        raise
                gs = r['data']['serverGameState']
                return {
                    'num_players':    gs.get('numConnectedPlayers', 0),
                    'player_limit':   gs.get('playerLimit', 0),
                    'session_name':   gs.get('activeSessionName', ''),
                    'is_paused':      gs.get('isGamePaused', False),
                    'tick_rate':      round(gs.get('averageTickRate', 0), 1),
                    'tech_tier':      gs.get('techTier', 0),
                    'total_duration': gs.get('totalGameDuration', 0),
                    'is_game_running': gs.get('isGameRunning', False),
                }
        except Exception:
            self._token = None
            return None

    async def is_running(self) -> bool:
        return await self.get_state() is not None

    async def wait_until_ready(self, timeout: int = 300) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.is_running():
                return True
            await asyncio.sleep(5)
        return False

    async def wait_until_stopped(self, timeout: int = 60) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self.is_running():
                return True
            await asyncio.sleep(3)
        return False

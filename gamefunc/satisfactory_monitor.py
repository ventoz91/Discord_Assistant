import asyncio
import logging
import os

from openai import AsyncOpenAI
from gamefunc.satisfactory import SatisfactoryServer

logger = logging.getLogger("bot.satisfactory_monitor")

_POLL_INTERVAL = 300  # seconds between tier checks


def _monitor_enabled() -> bool:
    return os.getenv('SATISFACTORY_EVENTS_ENABLED', 'true').strip().lower() != 'false'

_SYSTEM = (
    "You are {personality}. "
    "A factory milestone was just reached in Satisfactory. React in one enthusiastic sentence "
    "in character — no @mentions, no quotation marks, no asterisks for emphasis."
)


class SatisfactoryMonitor:
    def __init__(self, openai_api_key: str):
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._server = SatisfactoryServer()
        self._last_tier: int | None = None
        self._task: asyncio.Task | None = None

    def start(self, bot, channel_id: int):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._poll_loop(bot, channel_id))

    def stop(self):
        if self._task:
            self._task.cancel()

    async def _poll_loop(self, bot, channel_id: int):
        if not os.getenv('SATISFACTORY_SSH_HOST', ''):
            logger.info("SATISFACTORY_SSH_HOST not set — Satisfactory monitor disabled")
            return

        logger.info("Satisfactory monitor started (poll interval: %ds)", _POLL_INTERVAL)
        while True:
            try:
                if not _monitor_enabled():
                    await asyncio.sleep(_POLL_INTERVAL)
                    continue
                state = await self._server.get_state()
                if state and state.get('is_game_running'):
                    tier = state.get('tech_tier')
                    if tier is not None:
                        if self._last_tier is not None and tier > self._last_tier:
                            asyncio.create_task(self._announce(bot, channel_id, tier))
                        self._last_tier = tier
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Satisfactory monitor error: %s", e)
            await asyncio.sleep(_POLL_INTERVAL)

    async def _announce(self, bot, channel_id: int, tier: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            return
        personality = getattr(bot, 'chatgpt_behaviour', '')
        try:
            resp = await self._client.chat.completions.create(
                model=os.getenv('MODEL_CHAT', 'gpt-4o'),
                messages=[
                    {"role": "system", "content": _SYSTEM.format(personality=personality)},
                    {"role": "user",   "content": f"The factory just unlocked tech tier {tier}!"},
                ],
                max_completion_tokens=60,
                temperature=1.2,
            )
            await channel.send(resp.choices[0].message.content.strip())
        except Exception as e:
            logger.warning("Milestone announcement failed: %s", e)

"""The Morning Paper: a daily in-character recap per configured channel.

Disabled unless MORNING_PAPER_CHANNEL_IDS is set. Once per day, at or after
MORNING_PAPER_HOUR (server-local time), each configured channel gets a recap
of the last 24h — highlights, running jokes, anything left unresolved.
Channels with fewer than MORNING_PAPER_MIN_MESSAGES messages are skipped for
the day (no "nothing happened" spam). State in data/morning_paper_state.json
prevents double-posting across restarts.
"""

import asyncio
import datetime
import json
import logging
import os

logger = logging.getLogger("bot.morning_paper")

_STATE_PATH = os.path.join("data", "morning_paper_state.json")


def _load_state() -> dict:
    if not os.path.exists(_STATE_PATH):
        return {}
    with open(_STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _channel_ids() -> list[int]:
    raw = os.getenv("MORNING_PAPER_CHANNEL_IDS", "")
    return [int(c) for c in raw.split(",") if c.strip()]


def should_post(now: datetime.datetime, post_hour: int, last_posted_date: str | None) -> bool:
    """True when it's at/after post_hour and today's edition hasn't gone out."""
    if now.hour < post_hour:
        return False
    return last_posted_date != now.date().isoformat()


_PAPER_PROMPT = (
    "Write today's edition of your daily channel recap — a short, punchy, in-character "
    "\"morning paper\" covering the last 24 hours in this Discord channel. Structure it "
    "loosely as: the headline moment, 2-4 quick highlights (funny quotes, arguments, "
    "achievements, anything decided or left hanging), and if it fits, a one-line teaser "
    "about an ongoing thread. Attribute things to the right people. Keep it under 250 "
    "words. Do not invent events that aren't in the log.\n\n"
    "{threads_section}"
    "CHANNEL LOG (last 24h):\n{log}"
)


async def _compose_and_post(bot, channel_id: int) -> bool:
    """Build and post one channel's edition. Returns True if posted or skipped-for-day."""
    from AIfunc.responses import generate_gpt_response
    from chatbotfunc.debates import get_debate_context
    from chatbotfunc.utils import split_message

    channel = bot.get_channel(channel_id)
    if channel is None:
        logger.warning("morning paper: channel %d not found", channel_id)
        return True  # don't retry all day

    after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    lines = []
    async for message in channel.history(after=after, limit=500, oldest_first=True):
        if message.content:
            author = "you" if message.author == bot.user else message.author.display_name
            lines.append(f"{author}: {message.content}")

    min_messages = int(os.getenv("MORNING_PAPER_MIN_MESSAGES", "15"))
    if len(lines) < min_messages:
        logger.info("morning paper: channel %d quiet (%d msgs), skipping today", channel_id, len(lines))
        return True

    max_input = int(os.getenv("MORNING_PAPER_MAX_INPUT_CHARS", "12000"))
    log_block = "\n".join(lines)[-max_input:]

    threads = await asyncio.to_thread(get_debate_context, channel_id)
    threads_section = f"ONGOING THREADS YOU TRACK:\n{threads}\n\n" if threads else ""

    personality = (
        bot.personality_manager.get_channel_personality(channel_id)
        or bot.chatgpt_behaviour
    )
    text = await generate_gpt_response(
        [{"role": "user", "content": _PAPER_PROMPT.format(threads_section=threads_section, log=log_block)}],
        personality,
        max_completion_tokens=int(os.getenv("MORNING_PAPER_MAX_TOKENS", "600")),
    )
    if not text or text.startswith("An error occurred"):
        logger.warning("morning paper: generation failed for channel %d", channel_id)
        return False  # retry on next tick

    for chunk in split_message(f"📰 **The Morning Paper**\n{text}"):
        await channel.send(chunk)
    return True


async def morning_paper_loop(bot):
    """Background task: post each configured channel's daily edition. Start once."""
    channels = _channel_ids()
    if not channels:
        logger.info("morning paper disabled (MORNING_PAPER_CHANNEL_IDS not set)")
        return
    logger.info("morning paper loop started for %d channel(s)", len(channels))
    while True:
        await asyncio.sleep(300)
        try:
            post_hour = int(os.getenv("MORNING_PAPER_HOUR", "9"))
            now = datetime.datetime.now()
            state = await asyncio.to_thread(_load_state)
            for channel_id in _channel_ids():
                if not should_post(now, post_hour, state.get(str(channel_id))):
                    continue
                try:
                    if await _compose_and_post(bot, channel_id):
                        state[str(channel_id)] = now.date().isoformat()
                        await asyncio.to_thread(_save_state, state)
                except Exception:
                    logger.exception("morning paper failed for channel %d", channel_id)
        except Exception:
            logger.exception("morning paper loop error")

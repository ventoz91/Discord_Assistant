"""Reminders: JSON-backed store plus a background delivery loop.

Reminders are stored in data/reminders.json and survive restarts. The loop
wakes every REMINDER_CHECK_SECONDS (default 30), pops anything due, and
delivers it in character (plain fallback if the LLM call fails). Reminders
that came due while the bot was down are delivered on the first tick.
"""

import asyncio
import json
import logging
import os
import re
import time

logger = logging.getLogger("bot.reminders")

_REMINDERS_PATH = os.path.join("data", "reminders.json")

_DURATION_RE = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> int | None:
    """Parse '30m', '2h', '1d', '1h30m', '1w' etc. into seconds. None if invalid."""
    if not text:
        return None
    matches = _DURATION_RE.findall(text.strip())
    if not matches or "".join(f"{n}{u}" for n, u in matches).lower() != re.sub(r"\s+", "", text.strip()).lower():
        return None
    total = sum(int(n) * _UNIT_SECONDS[u.lower()] for n, u in matches)
    return total if total > 0 else None


def format_duration(seconds: int) -> str:
    parts = []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
        if len(parts) == 2:
            break
    return "".join(parts) or "0s"


def _load() -> dict:
    if not os.path.exists(_REMINDERS_PATH):
        return {"next_id": 1, "reminders": []}
    with open(_REMINDERS_PATH) as f:
        return json.load(f)


def _save(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(_REMINDERS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_reminder(channel_id: int, user_id: int, user_name: str, delay_seconds: int, text: str) -> dict:
    data = _load()
    reminder = {
        "id": data["next_id"],
        "channel_id": channel_id,
        "user_id": user_id,
        "user_name": user_name,
        "text": text,
        "created_ts": int(time.time()),
        "due_ts": int(time.time()) + delay_seconds,
    }
    data["next_id"] += 1
    data["reminders"].append(reminder)
    _save(data)
    return reminder


def list_reminders(user_id: int = None) -> list[dict]:
    """Pending reminders, soonest first. Filtered to one user if given."""
    reminders = _load()["reminders"]
    if user_id is not None:
        reminders = [r for r in reminders if r["user_id"] == user_id]
    return sorted(reminders, key=lambda r: r["due_ts"])


def cancel_reminder(reminder_id: int, user_id: int) -> dict | None:
    """Cancel a reminder by id — only its owner may. Returns the cancelled entry."""
    data = _load()
    for i, r in enumerate(data["reminders"]):
        if r["id"] == reminder_id and r["user_id"] == user_id:
            data["reminders"].pop(i)
            _save(data)
            return r
    return None


def pop_due(now: int = None) -> list[dict]:
    """Remove and return all reminders whose due time has passed."""
    now = now or int(time.time())
    data = _load()
    due = [r for r in data["reminders"] if r["due_ts"] <= now]
    if due:
        data["reminders"] = [r for r in data["reminders"] if r["due_ts"] > now]
        _save(data)
    return due


async def _deliver(bot, reminder: dict):
    channel = bot.get_channel(reminder["channel_id"])
    if channel is None:
        logger.warning("reminder %d: channel %d not found, dropping", reminder["id"], reminder["channel_id"])
        return
    mention = f"<@{reminder['user_id']}>"
    fallback = f"{mention} ⏰ **Reminder:** {reminder['text']}"

    late_secs = int(time.time()) - reminder["due_ts"]
    lateness = (
        f" You are delivering it {format_duration(late_secs)} late (you were offline) — briefly own that."
        if late_secs > 120 else ""
    )
    try:
        from AIfunc.responses import generate_gpt_response
        personality = (
            bot.personality_manager.get_channel_personality(channel.id)
            or bot.chatgpt_behaviour
        )
        prompt = (
            f"Deliver this reminder to {reminder['user_name']} now, in character and briefly "
            f"(1-3 sentences): \"{reminder['text']}\". They set it "
            f"{format_duration(reminder['due_ts'] - reminder['created_ts'])} ago.{lateness} "
            f"Address them as {mention}."
        )
        text = await generate_gpt_response(
            [{"role": "user", "content": prompt}], personality
        )
        if not text:
            text = fallback
        elif mention not in text:
            text = f"{mention} {text}"
    except Exception:
        logger.exception("in-character reminder delivery failed, using fallback")
        text = fallback
    try:
        await channel.send(text)
    except Exception:
        logger.exception("reminder %d: send failed", reminder["id"])


async def reminder_loop(bot):
    """Background task: deliver due reminders. Start once per process."""
    check_secs = int(os.getenv("REMINDER_CHECK_SECONDS", "30"))
    logger.info("reminder loop started (check interval: %ds)", check_secs)
    while True:
        await asyncio.sleep(check_secs)
        try:
            due = await asyncio.to_thread(pop_due)
            for reminder in due:
                await _deliver(bot, reminder)
        except Exception:
            logger.exception("reminder loop error")

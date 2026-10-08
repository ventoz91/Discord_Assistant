"""Daily SafeArr review-queue report.

Disabled unless SAFEARR_URL and SAFEARR_REPORT_CHANNEL_ID are set. Once per
day, at or after SAFEARR_REPORT_HOUR (server-local time), reads SafeArr's
GET /api/pending and posts how many downloads are waiting for review, per
show. Nothing is posted when the queue is empty. State in
data/safearr_report_state.json prevents double-posting across restarts.
"""

import asyncio
import datetime
import json
import logging
import os
import time

import aiohttp

from chatbotfunc.morning_paper import should_post

logger = logging.getLogger("bot.safearr_report")

_STATE_PATH = os.path.join("data", "safearr_report_state.json")
_MAX_TITLES = 8


def _load_state() -> dict:
    if not os.path.exists(_STATE_PATH):
        return {}
    with open(_STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _fmt_age(seconds: float) -> str:
    hours = int(seconds // 3600)
    if hours < 1:
        return "under an hour"
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24} days"


def format_report(summary: dict, url: str, now: float | None = None) -> str | None:
    """The message for one /api/pending response, or None when nothing waits."""
    reviewing = summary.get("reviewing", 0)
    if not reviewing:
        return None
    now = time.time() if now is None else now
    noun = "download" if reviewing == 1 else "downloads"
    lines = [f"🛡️ **SafeArr:** {reviewing} {noun} waiting for review"]
    titles = list((summary.get("by_title") or {}).items())
    if titles:
        shown = ", ".join(f"{t} ({n})" for t, n in titles[:_MAX_TITLES])
        if len(titles) > _MAX_TITLES:
            shown += f", +{len(titles) - _MAX_TITLES} more"
        lines.append(shown)
    extra = []
    if summary.get("flagged"):
        extra.append(f"⚠️ {summary['flagged']} flagged as likely wrong file")
    if summary.get("oldest_quarantined_at"):
        extra.append(f"oldest waiting {_fmt_age(now - summary['oldest_quarantined_at'])}")
    if extra:
        lines.append(" · ".join(extra))
    lines.append(f"<{url.rstrip('/')}/>")
    return "\n".join(lines)


async def _fetch_pending(url: str) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(f"{url.rstrip('/')}/api/pending") as resp:
            resp.raise_for_status()
            return await resp.json()


async def safearr_report_loop(bot):
    """Background task: post the daily review-queue count. Start once."""
    url = os.getenv("SAFEARR_URL", "")
    channel_id = int(os.getenv("SAFEARR_REPORT_CHANNEL_ID", "0") or 0)
    if not url or not channel_id:
        logger.info("safearr report disabled (SAFEARR_URL / SAFEARR_REPORT_CHANNEL_ID not set)")
        return
    logger.info("safearr report loop started for channel %d", channel_id)
    while True:
        await asyncio.sleep(300)
        try:
            post_hour = int(os.getenv("SAFEARR_REPORT_HOUR", "9"))
            now = datetime.datetime.now()
            state = await asyncio.to_thread(_load_state)
            if not should_post(now, post_hour, state.get("last_posted")):
                continue
            try:
                summary = await _fetch_pending(url)
            except Exception as e:
                logger.warning("safearr report: couldn't reach %s (%s), retrying", url, e)
                continue
            text = format_report(summary, url)
            if text:
                channel = bot.get_channel(channel_id)
                if channel is None:
                    logger.warning("safearr report: channel %d not found", channel_id)
                else:
                    await channel.send(text)
            state["last_posted"] = now.date().isoformat()
            await asyncio.to_thread(_save_state, state)
        except Exception:
            logger.exception("safearr report loop error")

"""SafeArr in Discord: a daily report and stuck-file alerts.

Disabled unless SAFEARR_URL and SAFEARR_REPORT_CHANNEL_ID are set. Both
read SafeArr's GET /api/pending.

- Daily, at or after SAFEARR_REPORT_HOUR (server-local time): downloads
  waiting for review per show, plus anything else needing a human (files
  stuck in intake, broken hardlinks, library titles a rule says should be
  adopted). Nothing is posted when all of that is zero.
- Every SAFEARR_ALERT_MINUTES (default 5): one message per file that newly
  got stuck in intake (e.g. a video ffmpeg can't decode), so it isn't
  noticed only a day later. Never includes screenshots.

State in data/safearr_report_state.json and safearr_alert_state.json
prevents double posts across restarts.
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
_ALERT_STATE_PATH = os.path.join("data", "safearr_alert_state.json")  # separate file: the two loops run independently
_MAX_TITLES = 8


def _load_state(path: str = _STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save_state(state: dict, path: str = _STATE_PATH):
    os.makedirs("data", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _fmt_age(seconds: float) -> str:
    hours = int(seconds // 3600)
    if hours < 1:
        return "under an hour"
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24} days"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def format_report(summary: dict, url: str, now: float | None = None) -> str | None:
    """The daily message for one /api/pending response, or None when there's
    nothing for a human to do.
    """
    reviewing = summary.get("reviewing", 0)
    stuck = len(summary.get("stuck") or [])
    broken = summary.get("broken_hardlinks") or 0
    candidates = summary.get("adopt_candidates") or 0
    if not (reviewing or stuck or broken or candidates):
        return None
    now = time.time() if now is None else now
    if reviewing:
        lines = [f"🛡️ **SafeArr:** {_plural(reviewing, 'download', 'downloads')} waiting for review"]
    else:
        lines = ["🛡️ **SafeArr:** nothing waiting for review"]
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
    if stuck:
        lines.append(f"🧱 {_plural(stuck, 'file is', 'files are')} stuck before review (see the dashboard)")
    if broken:
        lines.append(f"🔗 {_plural(broken, 'approved file is', 'approved files are')} no longer hardlinked: "
                     "run `safearr relink`")
    if candidates:
        lines.append(f"📥 {_plural(candidates, 'title matches', 'titles match')} a rule but isn't protected yet: "
                     f"<{url.rstrip('/')}/adopt>")
    lines.append(f"<{url.rstrip('/')}/>")
    return "\n".join(lines)


def new_stuck_alerts(summary: dict, alerted: set[str], url: str) -> tuple[list[str], set[str]]:
    """Messages for files stuck in intake that haven't been alerted yet, and
    the updated alerted set (paths no longer stuck are forgotten, so a file
    that gets stuck again alerts again).
    """
    stuck = {s["path"]: s for s in summary.get("stuck") or [] if s.get("path")}
    messages = []
    for path, s in stuck.items():
        if path in alerted:
            continue
        what = "can't be decoded" if s.get("kind") == "decode" else "couldn't be prepared for review"
        error = (s.get("error") or "")[:300]
        messages.append(f"⚠️ **SafeArr:** `{s.get('file') or path}` {what}.\n{error}\n<{url.rstrip('/')}/>")
    return messages, set(stuck)


async def _fetch_pending(url: str) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(f"{url.rstrip('/')}/api/pending") as resp:
            resp.raise_for_status()
            return await resp.json()


async def safearr_alert_loop(bot):
    """Background task: alert on files newly stuck in intake. Start once."""
    url = os.getenv("SAFEARR_URL", "")
    channel_id = int(os.getenv("SAFEARR_REPORT_CHANNEL_ID", "0") or 0)
    if not url or not channel_id:
        return
    interval = 60 * float(os.getenv("SAFEARR_ALERT_MINUTES", "5"))
    while True:
        await asyncio.sleep(interval)
        try:
            summary = await _fetch_pending(url)
        except Exception as e:
            logger.debug("safearr alerts: couldn't reach %s (%s)", url, e)
            continue
        try:
            state = await asyncio.to_thread(_load_state, _ALERT_STATE_PATH)
            messages, alerted = new_stuck_alerts(summary, set(state.get("alerted_stuck", [])), url)
            channel = bot.get_channel(channel_id)
            if messages and channel is None:
                logger.warning("safearr alerts: channel %d not found", channel_id)
                continue
            for text in messages:
                await channel.send(text)
            if alerted != set(state.get("alerted_stuck", [])):
                state["alerted_stuck"] = sorted(alerted)
                await asyncio.to_thread(_save_state, state, _ALERT_STATE_PATH)
        except Exception:
            logger.exception("safearr alert loop error")


async def safearr_report_loop(bot):
    """Background task: post the daily report. Start once."""
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

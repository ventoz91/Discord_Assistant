import asyncio
import datetime
import json
import logging
import os
import re
import time

logger = logging.getLogger("bot.debates")

_DEBATES_PATH = os.path.join("data", "debates.json")


def _load() -> dict:
    if not os.path.exists(_DEBATES_PATH):
        return {}
    with open(_DEBATES_PATH) as f:
        return json.load(f)


def _save(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(_DEBATES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_debate_context(channel_id: int) -> str | None:
    """Return a formatted block of ongoing debates/jokes for system-prompt injection.

    Only surfaces unresolved entries that haven't been brought up within the
    cooldown window, so Ralph doesn't hammer the same callback every message.
    """
    if os.getenv("DEBATE_TRACKING", "true").lower() != "true":
        return None

    data = _load()
    entries = data.get(str(channel_id), {}).get("entries", [])
    if not entries:
        return None

    cooldown_secs = float(os.getenv("DEBATE_SURFACE_COOLDOWN_DAYS", "3")) * 86400
    now = time.time()
    eligible = [
        e for e in entries
        if not e.get("resolved") and (now - e.get("last_surfaced_ts", 0)) >= cooldown_secs
    ]
    if not eligible:
        return None

    eligible.sort(key=lambda e: e.get("last_surfaced_ts", 0))
    max_inject = int(os.getenv("DEBATE_INJECT_MAX", "3"))

    lines = []
    for e in eligible[:max_inject]:
        kind = "running joke" if e.get("type") == "running_joke" else "unresolved debate"
        participants = ", ".join(e.get("participants") or []) or "the group"
        lines.append(f"- [{kind}] {e['topic']} ({participants}): {e['summary']}")
    return "\n".join(lines)


def mark_surfaced(channel_id: int, response_text: str):
    """Stamp last_surfaced_ts on entries whose topic appears to have been referenced.

    Heuristic: every significant word (len > 3) in the topic shows up in the
    response. Fuzzy on purpose — avoids a second LLM call just to confirm a callback.
    """
    if not response_text:
        return
    data = _load()
    ch_key = str(channel_id)
    entries = data.get(ch_key, {}).get("entries", [])
    if not entries:
        return

    lowered = response_text.lower()
    changed = False
    for e in entries:
        topic_words = [w for w in re.findall(r"\w+", e.get("topic", "").lower()) if len(w) > 3]
        if topic_words and all(w in lowered for w in topic_words):
            e["last_surfaced_ts"] = int(time.time())
            changed = True

    if changed:
        _save(data)


_EXTRACTION_PROMPT = """You're analyzing a chunk of Discord chat to track ONGOING DEBATES and RUNNING JOKES — \
things this group keeps coming back to: disagreements that never got settled, or bits/references \
that keep recurring. Only report things genuinely worth remembering — real recurring threads, not \
one-off comments.

Already tracked:
{existing}

Recent chat:
{chat}

Return ONLY a JSON array of actions. Each action is one of:
  {{"action": "new", "topic": "<short title>", "summary": "<1-2 sentence gist>", \
"type": "unresolved_debate" or "running_joke", "participants": ["name", ...]}}
  {{"action": "update", "id": <existing #>, "summary": "<refreshed gist reflecting the latest turn>"}}
  {{"action": "resolve", "id": <existing #>}}  // the group settled it or dropped it for good

Return [] if nothing in this chat qualifies."""


async def scan_channel(bot, channel_id: int, model: str):
    """Scan recent channel history for new/updated/resolved debates and running jokes."""
    from chatbotfunc.utils import async_chat_completion

    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    interval_hours = float(os.getenv("DEBATE_SCAN_INTERVAL_HOURS", "12"))
    min_messages = int(os.getenv("DEBATE_SCAN_MIN_MESSAGES", "20"))

    data = await asyncio.to_thread(_load)
    ch_key = str(channel_id)
    ch_data = data.setdefault(ch_key, {"entries": [], "last_scan_ts": 0, "next_id": 1})
    last_scan_ts = ch_data.get("last_scan_ts") or (time.time() - interval_hours * 3600)
    after = datetime.datetime.fromtimestamp(last_scan_ts, tz=datetime.timezone.utc)

    lines = []
    async for message in channel.history(after=after, limit=500, oldest_first=True):
        if message.content:
            lines.append(f"{message.author.display_name}: {message.content}")

    now = int(time.time())
    if len(lines) < min_messages:
        ch_data["last_scan_ts"] = now
        await asyncio.to_thread(_save, data)
        return

    max_input = int(os.getenv("DEBATE_SCAN_MAX_INPUT_CHARS", "12000"))
    text_block = "\n".join(lines)[-max_input:]

    entries = ch_data["entries"]
    existing = "\n".join(
        f"#{e['id']} [{e['type']}] {e['topic']}: {e['summary']} (resolved: {e['resolved']})"
        for e in entries
    ) or "none yet"

    try:
        response = await async_chat_completion(
            model=os.getenv("DEBATE_MODEL", model),
            messages=[{"role": "user", "content": _EXTRACTION_PROMPT.format(existing=existing, chat=text_block)}],
            max_completion_tokens=int(os.getenv("DEBATE_SCAN_MAX_TOKENS", "400")),
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", content, re.DOTALL)
        actions = json.loads(match.group()) if match else []
        if not isinstance(actions, list):
            actions = []
    except Exception:
        logger.exception("debate scan failed for channel %d", channel_id)
        return

    by_id = {e["id"]: e for e in entries}
    changed = False
    for act in actions:
        if not isinstance(act, dict):
            continue
        kind = act.get("action")

        if kind == "new":
            topic = (act.get("topic") or "").strip()
            if not topic:
                continue
            entry_type = act.get("type") if act.get("type") in ("unresolved_debate", "running_joke") else "unresolved_debate"
            entry = {
                "id": ch_data["next_id"],
                "topic": topic,
                "summary": (act.get("summary") or "").strip(),
                "type": entry_type,
                "participants": [p for p in (act.get("participants") or []) if isinstance(p, str)][:6],
                "first_seen_ts": now,
                "last_mentioned_ts": now,
                "last_surfaced_ts": 0,
                "resolved": False,
            }
            ch_data["next_id"] += 1
            entries.append(entry)
            by_id[entry["id"]] = entry
            changed = True

        elif kind in ("update", "resolve"):
            try:
                aid = int(act.get("id"))
            except (TypeError, ValueError):
                continue
            entry = by_id.get(aid)
            if not entry:
                continue
            if kind == "update":
                if act.get("summary"):
                    entry["summary"] = act["summary"].strip()
                entry["last_mentioned_ts"] = now
            else:
                entry["resolved"] = True
            changed = True

    max_entries = int(os.getenv("DEBATE_MAX_PER_CHANNEL", "15"))
    if len(entries) > max_entries:
        entries.sort(key=lambda e: (not e["resolved"], e["last_mentioned_ts"]), reverse=True)
        del entries[max_entries:]
        changed = True

    ch_data["entries"] = entries
    ch_data["last_scan_ts"] = now
    await asyncio.to_thread(_save, data)
    if changed:
        logger.info("channel %d: debate tracker updated (%d entries)", channel_id, len(entries))


async def debate_scanner_loop(bot, model: str):
    """Background task: periodically scan all channels for ongoing debates and running jokes."""
    from ragfunc.memory import list_channel_ids

    interval_hours = float(os.getenv("DEBATE_SCAN_INTERVAL_HOURS", "12"))
    while True:
        await asyncio.sleep(interval_hours * 3600)
        if os.getenv("DEBATE_TRACKING", "true").lower() != "true":
            continue
        logger.info("debate scanner: scanning all channels")
        for cid in list_channel_ids():
            try:
                await scan_channel(bot, cid, model)
            except Exception:
                logger.exception("debate scanner: unhandled error in channel %d", cid)

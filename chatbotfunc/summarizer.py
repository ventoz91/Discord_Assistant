import asyncio
import json
import logging
import os
import time

logger = logging.getLogger("bot.summarizer")

_STATE_PATH = os.path.join("data", "summarizer_state.json")


def _load_state() -> dict:
    if not os.path.exists(_STATE_PATH):
        return {}
    with open(_STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


async def summarize_channel(channel_id: int, model: str):
    """Summarize expiring messages for one channel, obeying skip/force rules.

    Skip logic: if fewer than SUMMARY_MIN_NEW_MESSAGES are expiring AND we've
    summarized within SUMMARY_FORCE_AFTER_DAYS days, skip this run. Once
    SUMMARY_FORCE_AFTER_DAYS days pass without a summary, run regardless of
    message count so nothing expires without being captured.
    """
    from ragfunc.memory import ChannelMemory, async_store_document
    from chatbotfunc.utils import async_chat_completion

    ttl_days = int(os.getenv("MESSAGE_TTL_DAYS", "30"))
    days_before = int(os.getenv("SUMMARY_DAYS_BEFORE_EXPIRY", "5"))
    min_messages = int(os.getenv("SUMMARY_MIN_NEW_MESSAGES", "10"))
    force_after_days = int(os.getenv("SUMMARY_FORCE_AFTER_DAYS", "5"))

    # Collect messages old enough that they'll expire within days_before days
    cutoff_ts = int(time.time()) - (ttl_days - days_before) * 86400

    mem = ChannelMemory(channel_id)
    ids, docs = await asyncio.to_thread(mem.get_expiring, cutoff_ts)

    if not docs:
        return

    state = await asyncio.to_thread(_load_state)
    ch_key = str(channel_id)
    last_ts = state.get(ch_key, {}).get("last_summary_ts", 0)
    days_since = (time.time() - last_ts) / 86400

    force = days_since >= force_after_days
    if len(docs) < min_messages and not force:
        logger.debug(
            "channel %d: %d expiring msgs < min %d, skipping (force in %.1fd)",
            channel_id, len(docs), min_messages, force_after_days - days_since,
        )
        return

    logger.info("channel %d: summarizing %d messages (force=%s)", channel_id, len(docs), force)

    max_input = int(os.getenv("SUMMARY_MAX_INPUT_CHARS", "12000"))
    max_tokens = int(os.getenv("SUMMARY_MAX_TOKENS", "500"))
    text_block = "\n".join(docs)[:max_input]

    prompt = (
        "Summarize the following Discord chat history into a compact narrative. "
        "Focus on: key topics discussed, decisions made, events mentioned, shared plans, "
        "running jokes, and anything memorable or distinctive about the group. "
        "Be concise but preserve what's unique and useful for future context.\n\n"
        f"Chat history:\n{text_block}"
    )

    try:
        response = await async_chat_completion(
            model=os.getenv("SUMMARY_MODEL", model),
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=max_tokens,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
    except Exception:
        logger.exception("summarization LLM call failed for channel %d", channel_id)
        return

    if not summary:
        return

    await async_store_document(
        channel_id,
        f"[Conversation summary — {time.strftime('%Y-%m-%d')}]\n{summary}",
        source="auto-summary",
    )
    await asyncio.to_thread(mem.delete_by_ids, ids)

    state.setdefault(ch_key, {})["last_summary_ts"] = int(time.time())
    await asyncio.to_thread(_save_state, state)
    logger.info("channel %d: stored summary, deleted %d messages", channel_id, len(ids))


async def summarizer_loop(model: str):
    """Background task: periodically scan all channels for expiring messages."""
    from ragfunc.memory import list_channel_ids

    interval_hours = float(os.getenv("SUMMARY_INTERVAL_HOURS", "24"))
    while True:
        await asyncio.sleep(interval_hours * 3600)
        if os.getenv("SUMMARY_ENABLED", "true").lower() != "true":
            continue
        logger.info("summarizer: scanning all channels")
        channel_ids = list_channel_ids()
        for cid in channel_ids:
            try:
                await summarize_channel(cid, model)
            except Exception:
                logger.exception("summarizer: unhandled error in channel %d", cid)

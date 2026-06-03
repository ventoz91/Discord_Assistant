import asyncio
import json
import logging
import os
import re
import time

logger = logging.getLogger("bot.profiles")

_PROFILE_PATH = os.path.join("data", "user_profiles.json")


def _load() -> dict:
    if not os.path.exists(_PROFILE_PATH):
        return {}
    with open(_PROFILE_PATH) as f:
        return json.load(f)


def _save(profiles: dict):
    os.makedirs("data", exist_ok=True)
    with open(_PROFILE_PATH, "w") as f:
        json.dump(profiles, f, indent=2)


def get_user_context(user_id: int, display_name: str) -> str | None:
    """Return a profile string for system-prompt injection, or None if no profile exists.

    Reads at call time so background updates are always reflected.
    """
    if os.getenv("USER_PROFILE_EXTRACTION", "true").lower() != "true":
        return None
    profiles = _load()
    uid = str(user_id)
    if uid not in profiles or not profiles[uid].get("facts"):
        return None
    max_inject = int(os.getenv("USER_PROFILE_INJECT_MAX", "10"))
    # Keep the most recently added facts (tail of list)
    facts = profiles[uid]["facts"][-max_inject:]
    return f"{display_name}: {'; '.join(facts)}"


async def extract_and_update(user_id: int, display_name: str, user_msg: str, bot_msg: str, model: str):
    """Background task: extract new facts from an exchange and merge into the user profile.

    Fires after the bot has already responded — never blocks the main flow.
    """
    if os.getenv("USER_PROFILE_EXTRACTION", "true").lower() != "true":
        return
    if not user_msg.strip() or not bot_msg.strip():
        return

    profiles = await asyncio.to_thread(_load)
    uid = str(user_id)
    existing = profiles.get(uid, {}).get("facts", [])
    existing_str = "; ".join(existing) if existing else "none yet"

    max_input = int(os.getenv("USER_PROFILE_MSG_CHARS", "500"))
    prompt = (
        f"Extract personal facts about the user '{display_name}' from their message ONLY.\n\n"
        f"RULES:\n"
        f"- Only extract facts the user explicitly stated about themselves (e.g. 'I like X', 'I play Y', 'I prefer Z').\n"
        f"- Do NOT infer preferences from the bot's reply. The bot's response reflects the whole channel conversation, "
        f"not just this user — something the bot joked about or engaged with may have been started by someone else.\n"
        f"- If the user just replied to others, reacted to a joke, or didn't share anything explicitly personal, return [].\n\n"
        f"Already known: {existing_str}\n\n"
        f"User's message: {user_msg[:max_input]}\n"
        f"Bot's reply (full channel context — do not infer user preferences from this): {bot_msg[:max_input]}\n\n"
        f"Return ONLY a JSON array of NEW short fact strings (under 15 words each) not already "
        f"covered by the known facts. Return [] if nothing new.\n"
        f'Example: ["prefers modded Minecraft", "building a Discord bot"]'
    )

    try:
        from chatbotfunc.utils import async_chat_completion
        response = await async_chat_completion(
            model=os.getenv("USER_PROFILE_MODEL", model),
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=int(os.getenv("USER_PROFILE_EXTRACT_TOKENS", "200")),
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if not match:
            return
        new_facts = json.loads(match.group())
        if not isinstance(new_facts, list):
            return
        new_facts = [f.strip() for f in new_facts if isinstance(f, str) and f.strip()]
    except Exception:
        logger.exception("profile extraction failed for %s", display_name)
        return

    if not new_facts:
        return

    if uid not in profiles:
        profiles[uid] = {"display_name": display_name, "facts": [], "last_updated": 0}

    profiles[uid]["display_name"] = display_name
    profiles[uid]["facts"].extend(new_facts)
    max_facts = int(os.getenv("USER_PROFILE_MAX_FACTS", "20"))
    profiles[uid]["facts"] = profiles[uid]["facts"][-max_facts:]
    profiles[uid]["last_updated"] = int(time.time())

    await asyncio.to_thread(_save, profiles)
    logger.info("profile updated for %s (+%d): %s", display_name, len(new_facts), new_facts)
